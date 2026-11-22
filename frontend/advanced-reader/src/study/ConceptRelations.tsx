/** Directional relationships share canonical map operations and durable retries. */
import { useState } from "react";
import type { Intent } from "../knowledge-map/model";
import { executeStudy } from "./api";
import type { ConceptDetail, Page, StudyContext } from "./api";
import { useStudyResource } from "./navigation";
import type { Navigate } from "./navigation";
import { StudyLink } from "./StudyLink";
import { useLocalForm } from "./useLocalForm";
import { useOperationScope } from "./useOperationScope";

export function ConceptRelations({
  context,
  concept,
  navigate,
  changed,
}: {
  context: StudyContext;
  concept: ConceptDetail;
  navigate: Navigate;
  changed: () => void;
}) {
  const scope = useOperationScope(context);
  const local = useLocalForm(
    "mathmongo-connect-v1-" + context.library_id + "-" + concept.key,
    () => ({
      operation_id: crypto.randomUUID(),
      target: "",
      target_title: "",
      relation_type: "requiere_concepto",
      reverse: false,
      pending: false,
    }),
  );
  const [query, setQuery] = useState(""),
    [message, setMessage] = useState(""),
    [sending, setSending] = useState(false);
  const choices = useStudyResource<{ relation_types: string[] }>(
    context,
    "/choices",
  );
  const targets = useStudyResource<Page<{ key: string; titulo: string }>>(
    context,
    "/concepts?" + new URLSearchParams({ q: query }),
  );
  const value = local.state;
  const connect = async () => {
    if (sending || !value.target) return;
    const pending = { ...value, pending: true };
    if (!local.set(pending)) return;
    const intent: Intent = {
      operation_id: value.operation_id,
      action: "connect",
      key: concept.key,
      target: value.target,
      relation_type: value.relation_type,
      reverse: value.reverse,
    };
    setSending(true);
    try {
      const result = await executeStudy(context, intent);
      if (!scope.active) return;
      setMessage(result.message);
      if (["saved", "conflict", "invalid"].includes(result.status))
        local.set({
          ...pending,
          pending: false,
          operation_id: crypto.randomUUID(),
        });
      if (result.status === "saved") changed();
    } catch (error) {
      if (scope.active) setMessage((error as Error).message);
    } finally {
      if (scope.active) setSending(false);
    }
  };
  return (
    <section aria-label="Relaciones del concepto">
      <h2>Relaciones</h2>
      {concept.relations?.map((edge, index) => (
        <p key={index}>
          {edge.from === concept.key ? "Saliente" : "Entrante"}:{" "}
          <StudyLink
            to={"/study/concepts/" + encodeURIComponent(edge.from)}
            navigate={navigate}
          >
            {edge.from_title || "Concepto de origen"}
          </StudyLink>{" "}
          → {edge.tipo.replaceAll("_", " ")} →{" "}
          <StudyLink
            to={"/study/concepts/" + encodeURIComponent(edge.to)}
            navigate={navigate}
          >
            {edge.to_title || "Concepto de destino"}
          </StudyLink>
        </p>
      ))}
      {!concept.relations?.length && (
        <p>Este concepto todavía no tiene relaciones.</p>
      )}
      <fieldset disabled={value.pending || sending}>
        <label>
          Buscar concepto para conectar
          <input
            value={query}
            onChange={(event) => setQuery(event.target.value)}
          />
        </label>
        <label>
          Concepto relacionado
          <select
            value={value.target}
            onChange={(event) =>
              local.set({
                ...value,
                target: event.target.value,
                target_title:
                  targets.data?.items.find(
                    (item) => item.key === event.target.value,
                  )?.titulo || "",
              })
            }
          >
            <option value="">Selecciona un concepto</option>
            {value.target &&
              !targets.data?.items.some(
                (item) => item.key === value.target,
              ) && (
                <option value={value.target}>
                  {value.target_title || "Concepto seleccionado"}
                </option>
              )}
            {targets.data?.items
              .filter((item) => item.key !== concept.key)
              .map((item) => (
                <option key={item.key} value={item.key}>
                  {item.titulo}
                </option>
              ))}
          </select>
        </label>
        <label>
          Tipo de relación
          <select
            value={value.relation_type}
            onChange={(event) =>
              local.set({ ...value, relation_type: event.target.value })
            }
          >
            {choices.data?.relation_types.map((type) => (
              <option key={type} value={type}>
                {type.replaceAll("_", " ")}
              </option>
            ))}
          </select>
        </label>
        <label>
          <input
            type="checkbox"
            checked={value.reverse}
            onChange={(event) =>
              local.set({ ...value, reverse: event.target.checked })
            }
          />
          Relación entrante hacia este concepto
        </label>
      </fieldset>
      <button
        type="button"
        disabled={sending || !value.target}
        onClick={() => void connect()}
      >
        {value.pending ? "Reintentar el mismo vínculo" : "Guardar relación"}
      </button>
      {(message || local.problem) && (
        <p role="status">{message || local.problem}</p>
      )}
    </section>
  );
}
