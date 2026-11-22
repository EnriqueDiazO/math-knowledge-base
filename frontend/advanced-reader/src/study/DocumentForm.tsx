import { useOperationScope } from "./useOperationScope";
/** File bytes stay in the user's chosen file; only an idempotent upload envelope persists. */
import { useState } from "react";
import { studyRequest } from "./api";
import type { StudyContext, SourceDetail } from "./api";
import { useLocalForm } from "./useLocalForm";

export function DocumentForm({
  context,
  source,
  done,
}: {
  context: StudyContext;
  source: SourceDetail;
  done: () => void;
}) {
  const scope = useOperationScope(context);
  const draft = useLocalForm(
    "mathmongo-document-v1-" + context.library_id + "-" + source.source_id,
    () => ({
      operation_id: crypto.randomUUID(),
      title: "",
      url: "",
      reference_id: "",
      filename: "",
      sha256: "",
      kind: "pdf",
      pending: false,
    }),
  );
  const [file, setFile] = useState<File | null>(null),
    [message, setMessage] = useState(""),
    [sending, setSending] = useState(false);
  const choose = async (file: File | null) => {
    if (!file) {
      setFile(null);
      return;
    }
    const hash = Array.from(
      new Uint8Array(
        await crypto.subtle.digest("SHA-256", await file.arrayBuffer()),
      ),
      (byte) => byte.toString(16).padStart(2, "0"),
    ).join("");
    if (
      draft.state.pending &&
      (hash !== draft.state.sha256 || file.name !== draft.state.filename)
    ) {
      setMessage(
        "Selecciona el mismo archivo del intento pendiente. No se reemplazará un documento que pudiera haberse guardado.",
      );
      return;
    }
    setFile(file);
    if (!draft.state.pending)
      draft.set({
        ...draft.state,
        filename: file.name,
        sha256: hash,
        title: draft.state.title || file.name,
      });
  };
  const save = async () => {
    if (sending) return;
    const value = { ...draft.state, pending: true };
    if (value.kind === "pdf" && !file) {
      setMessage(
        "Selecciona el PDF original para enviar o reconciliar este intento. Tu ficha y el identificador se conservan.",
      );
      return;
    }
    if (!draft.set(value)) return;
    setSending(true);
    try {
      if (value.kind === "pdf") {
        const params = new URLSearchParams({
          operation_id: value.operation_id,
          title: value.title,
          filename: value.filename,
          ...(value.reference_id ? { reference_id: value.reference_id } : {}),
        });
        const response = await fetch(
          "/api/study/v1/sources/" +
            encodeURIComponent(source.source_id) +
            "/documents/pdf?" +
            params,
          {
            method: "POST",
            credentials: "same-origin",
            redirect: "error",
            cache: "no-store",
            headers: {
              "Content-Type": "application/pdf",
              "X-MathMongo-Library": context.library_id,
            },
            body: file,
          },
        );
        const result = await response.json();
        if (!response.ok || typeof result.document_id !== "string")
          throw new Error(
            "No se confirmó el PDF. Conserva el archivo original y reintenta el mismo envío.",
          );
      } else
        await studyRequest(
          "/sources/" + encodeURIComponent(source.source_id) + "/documents/web",
          context,
          {
            operation_id: value.operation_id,
            title: value.title,
            url: value.url,
            reference_id: value.reference_id || null,
          },
        );
      if (!scope.active) return;
      draft.clear();
      done();
    } catch (error) {
      if (!scope.active) return;
      setMessage((error as Error).message);
    } finally {
      if (scope.active) setSending(false);
    }
  };
  const value = draft.state;
  return (
    <section>
      <h2>Asociar documento</h2>
      <form
        onSubmit={(event) => {
          event.preventDefault();
          void save();
        }}
      >
        <fieldset disabled={sending || value.pending}>
          <label>
            Tipo de documento
            <select
              value={value.kind}
              onChange={(event) =>
                draft.set({ ...value, kind: event.target.value })
              }
            >
              <option value="pdf">PDF</option>
              <option value="web">Página web</option>
            </select>
          </label>
          <label>
            Título del documento
            <input
              value={value.title}
              onChange={(event) =>
                draft.set({ ...value, title: event.target.value })
              }
              required
            />
          </label>
          <label>
            Referencia del documento
            <select
              value={value.reference_id}
              onChange={(event) =>
                draft.set({ ...value, reference_id: event.target.value })
              }
            >
              <option value="">Sin referencia asociada</option>
              {source.references.map((item, index) => (
                <option key={index} value={item.reference_id}>
                  {item.title}
                </option>
              ))}
            </select>
          </label>
          {value.kind === "web" && (
            <label>
              URL del documento
              <input
                type="url"
                required
                value={value.url}
                onChange={(event) =>
                  draft.set({ ...value, url: event.target.value })
                }
              />
            </label>
          )}
        </fieldset>
        {value.kind === "pdf" && (
          <label>
            Archivo PDF
            <input
              type="file"
              accept="application/pdf,.pdf"
              disabled={sending}
              onChange={(event) => void choose(event.target.files?.[0] ?? null)}
            />
          </label>
        )}
        {value.pending && !file && value.kind === "pdf" && (
          <p>
            Reanuda seleccionando «{value.filename}». Se comprobará que sus
            bytes no hayan cambiado.
          </p>
        )}
        {(message || draft.problem) && (
          <p role="alert">{message || draft.problem}</p>
        )}
        <button type="button" onClick={draft.download}>
          Descargar ficha del documento
        </button>
        <button type="submit" disabled={sending} className="primary-button">
          {sending
            ? "Asociando…"
            : value.pending
              ? "Reintentar el mismo documento"
              : "Asociar documento"}
        </button>
      </form>
    </section>
  );
}
