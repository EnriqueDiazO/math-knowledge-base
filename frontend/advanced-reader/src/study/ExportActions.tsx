/** Download canonical TEX projects or isolated PDFs; no server filesystem paths. */
import { useState } from "react";
import { studyBinary, downloadDocument, type StudyContext } from "./api";
import { useOperationScope } from "./useOperationScope";
export function ExportActions({
  context,
  conceptKeys = [],
  noteIds = [],
  notebookId,
  structuredFamily,
}: {
  context: StudyContext;
  conceptKeys?: string[];
  noteIds?: string[];
  notebookId?: string;
  structuredFamily?: "cornell" | "cpi";
}) {
  const scope = useOperationScope(context),
    [message, setMessage] = useState(""),
    [includeIds, setIncludeIds] = useState(false),
    [busy, setBusy] = useState(false);
  const run = async (format: "pdf" | "tex") => {
    if (busy) return;
    setBusy(true);
    setMessage(
      format === "pdf"
        ? "Compilando el PDF con aislamiento…"
        : "Preparando el proyecto LaTeX…",
    );
    try {
      const blob = await studyBinary(
        notebookId
          ? (structuredFamily
              ? "/structured/" + structuredFamily
              : "/notebook") +
              "/" +
              encodeURIComponent(notebookId) +
              "/export"
          : "/export",
        context,
        notebookId
          ? { format }
          : {
              format,
              concept_keys: conceptKeys,
              note_ids: noteIds,
              include_technical_ids: includeIds,
            },
      );
      if (!scope.active) return;
      downloadDocument(
        blob,
        "mathmongo-documentos." + (format === "pdf" ? "pdf" : "zip"),
      );
      setMessage(
        "Descarga preparada. Los documentos de la biblioteca se conservan.",
      );
    } catch (error) {
      if (scope.active) setMessage((error as Error).message);
    } finally {
      if (scope.active) setBusy(false);
    }
  };
  return (
    <section
      className="study-export-actions"
      aria-label={
        notebookId ? "Exportar entrada guardada" : "Exportar documentos"
      }
    >
      {notebookId ? (
        <p>
          Se exporta la versión guardada. Guarda primero si quieres incluir los
          cambios del borrador.
        </p>
      ) : (
        <label>
          <input
            type="checkbox"
            checked={includeIds}
            disabled={busy}
            onChange={(event) => setIncludeIds(event.target.checked)}
          />{" "}
          Incluir identificadores técnicos
        </label>
      )}
      <button
        type="button"
        disabled={
          busy || (!notebookId && !conceptKeys.length && !noteIds.length)
        }
        onClick={() => void run("tex")}
      >
        Exportar proyecto TEX
      </button>
      <button
        type="button"
        disabled={
          busy || (!notebookId && !conceptKeys.length && !noteIds.length)
        }
        onClick={() => void run("pdf")}
      >
        Exportar PDF
      </button>
      <p role="status">{message}</p>
    </section>
  );
}
