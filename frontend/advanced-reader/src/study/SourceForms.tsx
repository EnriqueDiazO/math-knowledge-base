import { useOperationScope } from "./useOperationScope";
import { useState } from "react";
import { studyRequest, StudyApiError } from "./api";
import type { StudyContext } from "./api";
import type { Navigate } from "./navigation";
import { useLocalForm } from "./useLocalForm";
import { StudyLink } from "./StudyLink";
import { AuthoringPreparation } from "./AuthoringPreparation";

const sourceTypes = {
  book: "Libro",
  article: "Artículo",
  thesis: "Tesis",
  web: "Página web",
  documentation: "Documentación",
  course: "Curso",
  corpus: "Corpus",
  report: "Informe",
  project: "Proyecto",
  bibliographic_collection: "Colección bibliográfica",
  other: "Otra fuente",
};


export function NewSourcePage({
  context,
  navigate,
  search,
}: {
  context: StudyContext;
  navigate: Navigate;
  search: string;
}) {
  const scope = useOperationScope(context);
  const draft = useLocalForm(
    "mathmongo-source-v1-" + context.library_id,
    () => ({
      operation_id: crypto.randomUUID(),
      name: "",
      source_type: "book",
      description: "",
      pending: false,
    }),
  );
  const [message, setMessage] = useState(""),
    [sending, setSending] = useState(false);
  const save = async () => {
    if (sending) return;
    const value = { ...draft.state, pending: true };
    if (!draft.set(value)) return;
    setSending(true);
    try {
      const payload = {
        operation_id: value.operation_id,
        name: value.name,
        source_type: value.source_type,
        description: value.description,
      };
      const result = await studyRequest<{ source_id: string }>(
        "/sources",
        context,
        payload,
      );
      if (!scope.active) return;
      draft.clear();
      const back = new URLSearchParams(search).get("return");
      if (back?.startsWith("/study/") && !back.startsWith("//")) {
        const url = new URL(back, location.origin);
        url.searchParams.set("source", result.source_id);
        navigate(url.pathname + url.search);
      } else navigate("/study/sources/" + encodeURIComponent(result.source_id));
    } catch (error) {
      if (!scope.active) return;
      setMessage((error as Error).message);
      if (
        error instanceof StudyApiError &&
        [
          "source_duplicate",
          "source_conflict",
          "invalid_study_request",
          "invalid_source",
          "authoring_preparation",
        ].includes(error.code)
      )
        draft.set({ ...value, pending: false });
    } finally {
      if (scope.active) setSending(false);
    }
  };
  return (
    <section>
      <StudyLink to="/study/library" navigate={navigate}>
        Volver a Biblioteca
      </StudyLink>
      <h1>Añadir fuente</h1>
      <p>
        Primero identifica la fuente de estudio. Podrás añadir su ficha
        bibliográfica y documentos en el siguiente paso.
      </p>
      <AuthoringPreparation context={context} />
      <form
        onSubmit={(event) => {
          event.preventDefault();
          void save();
        }}
      >
        <fieldset disabled={draft.state.pending || sending}>
          <label>
            Nombre de la fuente
            <input
              required
              maxLength={500}
              value={draft.state.name}
              onChange={(event) =>
                draft.set({ ...draft.state, name: event.target.value })
              }
            />
          </label>
          <label>
            Tipo de fuente
            <select
              value={draft.state.source_type}
              onChange={(event) =>
                draft.set({ ...draft.state, source_type: event.target.value })
              }
            >
              {Object.entries(sourceTypes).map(([value, label]) => (
                <option key={value} value={value}>
                  {label}
                </option>
              ))}
            </select>
          </label>
          <label>
            Descripción
            <textarea
              value={draft.state.description}
              onChange={(event) =>
                draft.set({ ...draft.state, description: event.target.value })
              }
            />
          </label>
        </fieldset>
        {draft.problem && (
          <p role="alert">
            {draft.problem}
            <button type="button" onClick={draft.download}>
              Descargar borrador
            </button>
            <button type="button" onClick={draft.restart}>
              Conservar copia y empezar otra ficha
            </button>
          </p>
        )}
        {message && <p role="alert">{message}</p>}
        <button type="submit" className="primary-button" disabled={sending}>
          {sending
            ? "Guardando fuente…"
            : draft.state.pending
              ? "Reintentar el mismo envío"
              : "Guardar fuente"}
        </button>
      </form>
    </section>
  );
}

