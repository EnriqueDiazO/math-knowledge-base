/** Selective BibTeX import with reviewed input, durable intent and per-entry outcomes. */
import { bibtexSelection } from "./bibtex-state";
import { AuthoringPreparation } from "./AuthoringPreparation";
import { useState } from "react";
import { studyRequest, type StudyContext } from "./api";
import { useLocalForm } from "./useLocalForm";
import { useOperationScope } from "./useOperationScope";
type Preview = {
  candidates: {
    entry_index: number;
    citekey: string;
    reference_data: { title?: string };
    warnings: string[];
  }[];
  errors: { message: string }[];
};
export function BibtexImport({
  context,
  sourceId,
  done,
}: {
  context: StudyContext;
  sourceId: string;
  done: () => void;
}) {
  const scope = useOperationScope(context),
    draft = useLocalForm(
      "mathmongo-bibtex-v1-" + context.library_id + sourceId,
      () => ({
        operation_id: crypto.randomUUID(),
        content: "",
        selection: "[]",
      }),
    );
  const [preview, setPreview] = useState<Preview>(),
    [message, setMessage] = useState(""),
    [busy, setBusy] = useState(false);
  const root = "/sources/" + encodeURIComponent(sourceId) + "/bibtex";
  const run = async (importing: boolean) => {
    if (busy || !draft.set(draft.state)) return;
    setBusy(true);
    try {
      const payload = {
        operation_id: draft.state.operation_id,
        content: draft.state.content,
        selected: bibtexSelection(draft.state.selection) || [],
      };
      if (importing) {
        const result = await studyRequest<{
          items: { entry_index: number; status: string }[];
          saved: number;
        }>(root + "/import", context, payload);
        if (!scope.active) return;
        const failures = result.items.filter((item) => item.status !== "saved");
        setMessage(
          result.saved +
            " referencias confirmadas." +
            (failures.length
              ? " Hay coincidencias o conflictos en las entradas " +
                failures.map((item) => item.entry_index + 1).join(", ") +
                ". Revisa las referencias existentes; el texto se conserva."
              : ""),
        );
        if (!failures.length) {
          draft.clear();
          done();
        }
      } else {
        const result = await studyRequest<Preview>(
          root + "/preview",
          context,
          payload,
        );
        if (scope.active) setPreview(result);
      }
    } catch (error) {
      if (scope.active) setMessage((error as Error).message);
    } finally {
      if (scope.active) setBusy(false);
    }
  };
  const selected = bibtexSelection(draft.state.selection);
  if (!selected)
    return (
      <aside role="alert">
        <p>
          No se pudo recuperar la selección. El BibTeX original se conserva;
          descarga una copia antes de reiniciar.
        </p>
        <button onClick={draft.download}>Descargar borrador BibTeX</button>
        <button onClick={draft.restart}>Reiniciar con copia</button>
      </aside>
    );
  return (
    <section>
      <h2>Importar referencias BibTeX</h2>
      <AuthoringPreparation context={context} />
      <p>
        Pega el contenido y revisa las entradas. Sólo se importarán las que
        selecciones; las coincidencias no se fusionan.
      </p>
      <label>
        Contenido BibTeX
        <textarea
          value={draft.state.content}
          disabled={busy}
          onChange={(event) => {
            draft.set({
              ...draft.state,
              content: event.target.value,
              selection: "[]",
            });
            setPreview(undefined);
          }}
        />
      </label>
      <button
        type="button"
        disabled={busy || !draft.state.content.trim()}
        onClick={() => void run(false)}
      >
        Revisar entradas BibTeX
      </button>
      {preview && (
        <div>
          {preview.errors.map((error, index) => (
            <p role="alert" key={index}>
              {error.message}
            </p>
          ))}
          {preview.candidates.map((item) => (
            <label key={item.entry_index}>
              <input
                type="checkbox"
                checked={selected.includes(item.entry_index)}
                onChange={(event) =>
                  draft.set({
                    ...draft.state,
                    selection: JSON.stringify(
                      event.target.checked
                        ? [...selected, item.entry_index]
                        : selected.filter(
                            (index) => index !== item.entry_index,
                          ),
                    ),
                  })
                }
              />
              {item.reference_data.title || item.citekey}{" "}
              {item.warnings.join("; ")}
            </label>
          ))}
          <button
            type="button"
            disabled={busy || !selected.length}
            onClick={() => void run(true)}
          >
            Importar referencias seleccionadas
          </button>
        </div>
      )}
      <p role="status">{message || draft.problem}</p>
      <button type="button" onClick={draft.download}>
        Descargar borrador BibTeX
      </button>
    </section>
  );
}
