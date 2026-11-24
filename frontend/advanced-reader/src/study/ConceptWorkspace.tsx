import { useOperationScope } from "./useOperationScope";
/** Direct creation and revision-bound editing reuse the mathematical document port. */
import { useRef, useState } from "react";
import { DraftVault } from "../knowledge-map/drafts";
import { intention } from "../knowledge-map/model";
import type { Draft, Intent } from "../knowledge-map/model";
import type { DocumentEditor } from "../knowledge-map/document-editor";
import { emptyLocator } from "../knowledge-map/bibliography";
import { conceptTypes } from "../knowledge-map/concept-types";
import { DocumentSurface } from "./DocumentSurface";
import { executeStudy } from "./api";
import type { StudyContext, ConceptDetail, SourceDetail } from "./api";
import { useStudyResource } from "./navigation";
import type { Navigate } from "./navigation";
import { StudyLink } from "./StudyLink";
import { SourcePicker } from "./SourcePicker";
import { AuthoringPreparation } from "./AuthoringPreparation";

type ConceptDraft = Draft & { pending?: Intent };
export function ConceptEditorPage({
  context,
  navigate,
  search,
  conceptKey,
}: {
  context: StudyContext;
  navigate: Navigate;
  search: string;
  conceptKey?: string;
}) {
  const resource = useStudyResource<ConceptDetail>(
    context,
    conceptKey
      ? "/concepts/detail?" + new URLSearchParams({ key: conceptKey })
      : "/context",
  );
  if (conceptKey && !resource.data)
    return (
      <p role={resource.error ? "alert" : "status"}>
        {resource.error || "Abriendo el documento…"}
      </p>
    );
  return (
    <ConceptWorkspace
      key={context.library_id + conceptKey + search}
      context={context}
      navigate={navigate}
      search={search}
      concept={conceptKey ? resource.data : undefined}
    />
  );
}
function ConceptWorkspace({
  context,
  navigate,
  search,
  concept,
}: {
  context: StudyContext;
  navigate: Navigate;
  search: string;
  concept?: ConceptDetail;
}) {
  const scope = useOperationScope(context);
  const [vault] = useState(
    () => new DraftVault(context.library_id, "study-concepts"),
  );
  const [draft, setDraft] = useState<ConceptDraft>(() => {
    const params = new URLSearchParams(search),
      id = concept ? "edit-" + concept.key : params.get("draft") || "new";
    const old = vault.get(id) as ConceptDraft | undefined;
    const value: ConceptDraft = old ?? {
      id,
      action: concept ? "edit" : "create",
      title: concept?.titulo || "",
      content: concept?.contenido_latex || "",
      type: concept?.tipo || "definicion",
      comment: concept?.comentario || "",
      categories: concept?.categorias?.join(", ") || "",
      source: concept?.source_id || params.get("source") || "",
      origin: concept?.key || "",
      target: "",
      relation: "requiere_concepto",
      reverse: false,
      revision: concept?.revision || "",
      point: [0, 0, 1],
      referenceId: concept?.reference_id || undefined,
      referenceLocator: concept?.reference_locator ?? undefined,
    };
    if (!concept && !value.pending && params.get("source"))
      value.source = params.get("source")!;
    vault.put(value);
    return value;
  });
  const value = useRef(draft),
    composer = useRef<DocumentEditor | null>(null);
  const finished = useRef(false);
  const [initial] = useState(() => ({
    content: draft.content,
    snapshot: draft.document,
  }));
  const [message, setMessage] = useState(""),
    [sending, setSending] = useState(false),
    [existing, setExisting] = useState("");
  const bibliography = useStudyResource<SourceDetail>(
    context,
    draft.source ? "/sources/" + encodeURIComponent(draft.source) : "/context",
  );
  const remember = (next: ConceptDraft) => {
    value.current = next;
    vault.put(next);
    setDraft(next);
  };
  const save = async () => {
    if (sending) return;
    let current = value.current;
    if (!current.pending) {
      if (
        !current.title.trim() ||
        (!concept && !current.source) ||
        !composer.current?.value().trim()
      ) {
        setMessage(
          "Escribe un nombre, elige la fuente y desarrolla el contenido. El borrador se conserva.",
        );
        return;
      }
      if (!composer.current.valid()) {
        setMessage(
          "La fórmula está en elaboración. Complétala antes de guardar; el borrador se conserva.",
        );
        return;
      }
      current = {
        ...current,
        content: composer.current.value(),
        document: composer.current.snapshot(),
      };
      const payload = intention(current, crypto.randomUUID());
      if (concept && current.categories === concept.categorias.join(", "))
        payload.categorias = structuredClone(concept.categorias);
      if (
        concept &&
        current.referenceId === (concept.reference_id || undefined) &&
        JSON.stringify(current.referenceLocator ?? emptyLocator()) ===
          JSON.stringify(concept.reference_locator ?? emptyLocator())
      ) {
        delete payload.reference_id;
        delete payload.reference_locator;
      }
      current = { ...current, pending: payload };
      remember(current);
    }
    vault.put(current);
    if (!vault.available) {
      setMessage(
        "No se pudo conservar el intento. Recupera el almacenamiento o descarga el borrador antes de guardar.",
      );
      return;
    }
    setSending(true);
    setMessage("Guardando concepto…");
    try {
      const result = await executeStudy(context, current.pending!);
      if (!scope.active) return;
      if (result.status === "saved" && result.key) {
        finished.current = true;
        vault.discard(current.id!);
        navigate("/study/concepts/" + encodeURIComponent(result.key));
      } else {
        setMessage(result.message);
        if (result.status === "duplicate") setExisting(result.key ?? "");
        if (["invalid", "conflict", "duplicate"].includes(result.status))
          remember({ ...current, pending: undefined });
      }
    } catch (error) {
      setMessage((error as Error).message);
    } finally {
      setSending(false);
    }
  };
  const back =
    "/study/concepts/new?" + new URLSearchParams({ draft: draft.id! });
  return (
    <section className="study-writing">
      <StudyLink to="/study/concepts" navigate={navigate}>
        Volver a Conceptos
      </StudyLink>
      <h1>{concept ? "Editar concepto" : "Crear concepto"}</h1>
      <p>
        El contenido se conserva como LaTeX. Guardar confirma el documento en
        esta biblioteca.
      </p>
      <AuthoringPreparation context={context} />
      <fieldset disabled={!!draft.pending || sending}>
        <label>
          Nombre del concepto
          <input
            value={draft.title}
            maxLength={500}
            onChange={(event) =>
              remember({ ...value.current, title: event.target.value })
            }
          />
        </label>
        <label>
          Tipo matemático
          <select
            disabled={!!concept}
            value={draft.type}
            onChange={(event) =>
              remember({ ...value.current, type: event.target.value })
            }
          >
            {Object.entries(conceptTypes).map(([key, type]) => (
              <option value={key} key={key}>
                {type.label}
              </option>
            ))}
          </select>
        </label>
        {concept ? (
          <p>
            Fuente original: {concept.source}. Su identidad y tipo se conservan
            durante esta edición.
          </p>
        ) : (
          <>
            <SourcePicker
              context={context}
              value={draft.source}
              selectedName={bibliography.data?.name}
              choose={(source) =>
                remember({
                  ...value.current,
                  source,
                  referenceId: undefined,
                  referenceLocator: undefined,
                })
              }
            />
            <StudyLink
              to={"/study/sources/new?" + new URLSearchParams({ return: back })}
              navigate={navigate}
            >
              + Registrar fuente y volver al borrador
            </StudyLink>
          </>
        )}
        <details>
          <summary>Referencia y organización</summary>
          <label>
            Referencia bibliográfica
            <select
              value={draft.referenceId || ""}
              onChange={(event) =>
                remember({
                  ...value.current,
                  referenceId: event.target.value || undefined,
                })
              }
            >
              <option value="">Conservar sin nueva cita</option>
              {bibliography.data?.references?.map((reference, index) => (
                <option key={index} value={reference.reference_id}>
                  {reference.title}
                </option>
              ))}
            </select>
          </label>
          <label>
            Localizador de página
            <input
              disabled={!draft.referenceId}
              value={draft.referenceLocator?.printed_page || ""}
              onChange={(event) =>
                remember({
                  ...value.current,
                  referenceLocator: {
                    ...emptyLocator(),
                    ...draft.referenceLocator,
                    printed_page: event.target.value,
                  },
                })
              }
            />
          </label>
          <label>
            Categorías separadas por comas
            <input
              value={draft.categories}
              onChange={(event) =>
                remember({ ...value.current, categories: event.target.value })
              }
            />
          </label>
          <label>
            Comentario
            <textarea
              value={draft.comment}
              onChange={(event) =>
                remember({ ...value.current, comment: event.target.value })
              }
            />
          </label>
        </details>
      </fieldset>
      <div inert={!!draft.pending}>
        <DocumentSurface
          context={context}
          initial={initial.content}
          snapshot={initial.snapshot}
          editorRef={composer}
          changed={(content, document) => {
            if (finished.current) return;
            value.current = { ...value.current, content, document };
            vault.put(value.current);
          }}
        />
      </div>
      {message && <p role="status">{message}</p>}
      {!vault.available && (
        <p role="alert">
          El navegador no pudo conservar el borrador. Mantén el documento
          abierto hasta descargarlo.
        </p>
      )}
      {existing && (
        <StudyLink
          to={"/study/concepts/" + encodeURIComponent(existing)}
          navigate={navigate}
        >
          Revisar concepto existente; el borrador se conserva
        </StudyLink>
      )}
      <div className="study-document-actions">
        <button
          type="button"
          className="primary-button"
          disabled={sending}
          onClick={() => void save()}
        >
          {sending
            ? "Guardando…"
            : draft.pending
              ? "Reintentar el mismo envío"
              : "Guardar concepto"}
        </button>
        <StudyLink to="/study/concepts" navigate={navigate}>
          Conservar borrador y volver
        </StudyLink>
      </div>
      <p>
        Borrador local conservado. Sólo el guardado confirmado modifica el
        concepto.
      </p>
    </section>
  );
}
