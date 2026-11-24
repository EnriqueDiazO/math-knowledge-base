/** Progressive academic metadata editing, recoverable drafts and explicit conflict review. */
import { useState } from "react";
import { studyRequest, type StudyContext } from "./api";
import { useStudyResource } from "./navigation";
import { useLocalForm } from "./useLocalForm";
import { useOperationScope } from "./useOperationScope";
import { ReferencePicker } from "./ReferencePicker";
import { AuthoringPreparation } from "./AuthoringPreparation";
import {
  catalogChanges,
  catalogValues,
  rebaseCatalog,
  metadataFields,
  type CatalogKind,
  type CatalogRecord,
  type MetadataField,
} from "./catalog-fields";

export function CatalogEditor({
  context,
  sourceId,
  kind,
  identity,
  done,
}: {
  context: StudyContext;
  sourceId: string;
  kind: CatalogKind;
  identity: string;
  done: () => void;
}) {
  const path =
    "/sources/" +
    encodeURIComponent(sourceId) +
    (kind === "source"
      ? "/profile"
      : "/" +
        (kind === "reference" ? "references" : "documents") +
        "/" +
        encodeURIComponent(identity));
  const resource = useStudyResource<CatalogRecord>(context, path);
  if (resource.error)
    return (
      <p role="alert">
        {resource.error}{" "}
        <button onClick={resource.retry}>Reintentar ficha</button>
      </p>
    );
  return resource.data ? (
    <MetadataEditor
      key={context.library_id + kind + identity}
      context={context}
      kind={kind}
      identity={identity}
      path={path}
      initial={resource.data}
      done={done}
    />
  ) : (
    <p role="status">Abriendo los datos…</p>
  );
}
function MetadataEditor({
  context,
  kind,
  identity,
  path,
  initial,
  done,
}: {
  context: StudyContext;
  kind: CatalogKind;
  identity: string;
  path: string;
  initial: CatalogRecord;
  done: () => void;
}) {
  const scope = useOperationScope(context),
    draft = useLocalForm(
      "mathmongo-catalog-edit-v1-" + context.library_id + path,
      () => ({
        original_json: JSON.stringify(initial),
        values_json: JSON.stringify(catalogValues(kind, initial)),
        pending_json: "",
      }),
    );
  const [message, setMessage] = useState(""),
    [busy, setBusy] = useState(false),
    [current, setCurrent] = useState<CatalogRecord>(),
    [shared, setShared] = useState(false);
  let before: CatalogRecord, values: Record<string, string>;
  try {
    before = JSON.parse(draft.state.original_json);
    values = JSON.parse(draft.state.values_json);
    if (
      !before.revision ||
      !values ||
      typeof values !== "object" ||
      Array.isArray(values) ||
      Object.values(values).some((value) => typeof value !== "string")
    )
      throw new Error("draft");
    catalogValues(kind, before);
  } catch {
    return (
      <aside role="alert">
        <p>
          No se pudo reconstruir la ficha. Conserva una copia del borrador antes
          de reiniciar.
        </p>
        <button onClick={draft.download}>Descargar borrador</button>
        <button onClick={draft.restart}>Reiniciar con copia</button>
      </aside>
    );
  }
  const save = async () => {
    if (busy) return;
    const changes = catalogChanges(kind, before, values);
    if (!draft.state.pending_json && !Object.keys(changes).length) {
      setMessage("No hay cambios que guardar.");
      return;
    }
    if (
      kind === "reference" &&
      (before.source_ids?.length || 0) > 1 &&
      !shared &&
      !draft.state.pending_json
    ) {
      setMessage("Confirma el cambio de la referencia compartida.");
      return;
    }
    const payload = draft.state.pending_json
      ? JSON.parse(draft.state.pending_json)
      : { revision: before.revision, changes, acknowledge_shared: shared };
    if (!draft.set({ ...draft.state, pending_json: JSON.stringify(payload) }))
      return;
    setBusy(true);
    try {
      const confirmed = await studyRequest<CatalogRecord>(
        path,
        context,
        payload,
      );
      if (!scope.active) return;
      const id =
        confirmed[
          kind === "source"
            ? "source_id"
            : kind === "reference"
              ? "reference_id"
              : "document_id"
        ];
      if (id !== identity)
        throw new Error(
          "No se confirmó la ficha solicitada. El borrador se conserva.",
        );
      draft.clear();
      done();
    } catch (error) {
      if (scope.active) setMessage((error as Error).message);
    } finally {
      if (scope.active) setBusy(false);
    }
  };
  const review = async () => {
    setBusy(true);
    try {
      const record = await studyRequest<CatalogRecord>(path, context);
      if (scope.active) setCurrent(record);
    } catch (error) {
      if (scope.active) setMessage((error as Error).message);
    } finally {
      if (scope.active) setBusy(false);
    }
  };
  const field = (item: MetadataField) =>
    item.key === "reference_id" ? (
      <ReferencePicker
        key={item.key}
        context={context}
        sourceId={String(initial.source_id)}
        value={values.reference_id || ""}
        changed={(value) => change(item.key, value)}
      />
    ) : (
      <label key={item.key}>
        {item.label}
        {item.choices ? (
          <select
            value={values[item.key] || ""}
            onChange={(event) => change(item.key, event.target.value)}
          >
            {Object.entries(item.choices).map(([value, label]) => (
              <option key={value} value={value}>
                {label}
              </option>
            ))}
          </select>
        ) : item.multiline ? (
          <textarea
            value={values[item.key] || ""}
            onChange={(event) => change(item.key, event.target.value)}
          />
        ) : (
          <input
            type={item.type || "text"}
            value={values[item.key] || ""}
            onChange={(event) => change(item.key, event.target.value)}
          />
        )}
      </label>
    );
  const change = (key: string, value: string) =>
    draft.set({
      ...draft.state,
      values_json: JSON.stringify({ ...values, [key]: value }),
    });
  return (
    <section aria-label="Editar metadatos">
      <h2>
        {kind === "source"
          ? "Editar fuente"
          : kind === "reference"
            ? "Editar referencia"
            : "Editar documento"}
      </h2>
      <AuthoringPreparation context={context} />
      <p>
        Se conserva la identidad y el contenido asociado. Sólo se envían los
        campos que has cambiado.
      </p>
      <form
        onSubmit={(event) => {
          event.preventDefault();
          void save();
        }}
      >
        <fieldset disabled={busy || !!draft.state.pending_json}>
          {metadataFields[kind].filter((item) => !item.advanced).map(field)}
          <details>
            <summary>Más datos bibliográficos</summary>
            {metadataFields[kind].filter((item) => item.advanced).map(field)}
          </details>
        </fieldset>
        {kind === "reference" && (before.source_ids?.length || 0) > 1 && (
          <label>
            <input
              type="checkbox"
              checked={shared}
              disabled={busy || !!draft.state.pending_json}
              onChange={(event) => setShared(event.target.checked)}
            />
            Aplicar estos cambios a la referencia compartida por{" "}
            {before.source_ids!.length} fuentes
          </label>
        )}
        <p role="status">{message || draft.problem}</p>
        <button className="primary-button" type="submit" disabled={busy}>
          {busy
            ? "Guardando datos…"
            : draft.state.pending_json
              ? "Reintentar el mismo guardado"
              : "Guardar cambios"}
        </button>
        <button type="button" onClick={draft.download}>
          Descargar borrador
        </button>
        <button type="button" disabled={busy} onClick={() => void review()}>
          Revisar versión actual
        </button>
      </form>
      {current && (
        <aside>
          <h3>Versión actual y cambios locales</h3>
          <p>
            Los campos que no editaste se recuperarán de la versión actual.
            Revisa las diferencias antes de volver a guardar.
          </p>
          {metadataFields[kind]
            .filter(
              (item) =>
                values[item.key] !== catalogValues(kind, current)[item.key],
            )
            .map((item) => (
              <p key={item.key}>
                <strong>{item.label}</strong>: actual «
                {catalogValues(kind, current)[item.key]}»; tu borrador «
                {values[item.key]}».
              </p>
            ))}
          <button
            onClick={() => {
              draft.set({
                original_json: JSON.stringify(current),
                values_json: JSON.stringify(
                  rebaseCatalog(kind, before, values, current),
                ),
                pending_json: "",
              });
              setCurrent(undefined);
              setShared(false);
              setMessage(
                "Borrador conservado sobre la versión revisada. Revisa los campos y guarda para confirmar.",
              );
            }}
          >
            Continuar editando sobre esta versión
          </button>
        </aside>
      )}
    </section>
  );
}
