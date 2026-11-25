/** Revision-bound note management; pending operations remain retryable without the deleted page. */
import { useState } from "react";
import {
  downloadDocument,
  studyRequest,
  StudyApiError,
  type StudyContext,
} from "./api";
import { diaryDraftPrefix, restoreDiary } from "./diary-storage";
import { useLocalForm } from "./useLocalForm";
import { useOperationScope } from "./useOperationScope";
import type { Navigate } from "./navigation";
import {
  prepareNoteAction,
  confirmedNoteRoute,
  type NoteActionFamily as Family,
  type NoteActionDescriptor as Descriptor,
  type NoteActionResponse,
  type NoteActionIntent as Intent,
} from "./note-action-state";
export function SavedNoteActions({
  context,
  family,
  identity,
  note,
  navigate,
  refresh,
}: {
  context: StudyContext;
  family: Family;
  identity: string;
  note?: Descriptor;
  navigate: Navigate;
  refresh: () => void;
}) {
  const scope = useOperationScope(context);
  const form = useLocalForm(
    "mathmongo-note-actions-v1-" +
      context.library_id +
      "-" +
      family +
      "-" +
      identity,
    () => ({
      mode: "",
      reviewTitle: "",
      revision: "",
      typed: "",
      title: "",
      pending: "",
    }),
  );
  const [message, setMessage] = useState(""),
    [busy, setBusy] = useState(false);
  const root = family === "diary" ? "/notebook" : "/structured/" + family;
  const select = (mode: string) => {
    if (!note || form.state.pending) return;
    form.set({
      mode,
      reviewTitle: note.title,
      revision: note.revision,
      typed: "",
      title: "Copia de " + (note.title || "Nota"),
      pending: "",
    });
    setMessage("");
  };
  const send = async () => {
    if (busy || form.problem) return;
    try {
      const pending: Intent | undefined = form.state.pending
        ? JSON.parse(form.state.pending)
        : prepareNoteAction(form.state, note);
      if (!pending) return;
      if (
        !form.state.pending &&
        !form.set({ ...form.state, pending: JSON.stringify(pending) })
      )
        return;
      setBusy(true);
      setMessage("Esperando confirmación de la biblioteca…");
      const result = await studyRequest<NoteActionResponse>(
        root + "/" + encodeURIComponent(identity) + "/actions",
        context,
        pending,
      );
      if (!scope.active) return;
      const route = confirmedNoteRoute(family, identity, pending, result);
      form.clear();
      navigate(route);
    } catch (error) {
      if (!scope.active) return;
      if (
        error instanceof StudyApiError &&
        ["catalog_conflict", "invalid_study_request"].includes(error.code)
      )
        form.set({ ...form.state, pending: "" });
      setMessage(
        error instanceof SyntaxError
          ? "No pudimos leer la solicitud local. Descárgala para conservarla y consulta la nota guardada antes de decidir cómo continuar."
          : (error as Error).message,
      );
    } finally {
      if (scope.active) setBusy(false);
    }
  };
  const downloadDraft = async () => {
    const key =
      family === "diary"
        ? diaryDraftPrefix(context.library_id) + identity
        : "mathmongo-structured-v1-" +
          context.library_id +
          "-" +
          family +
          "-" +
          identity;
    try {
      const raw =
        family === "diary"
          ? (await restoreDiary(key)).raw
          : localStorage.getItem(key);
      if (!scope.active) return;
      if (raw === null) {
        setMessage(
          "No encontramos un borrador local de esta nota en este navegador.",
        );
        return;
      }
      downloadDocument(
        new Blob([raw], { type: "application/json" }),
        "mathmongo-borrador-nota.json",
      );
    } catch {
      setMessage(
        "No pudimos leer el borrador local. Conserva esta ventana y permite el almacenamiento del navegador.",
      );
    }
  };
  if (!note && !form.state.pending && !form.problem)
    return (
      <>
        <button type="button" onClick={() => void downloadDraft()}>
          Descargar borrador local de esta nota
        </button>
        {message && <p role="status">{message}</p>}
      </>
    );
  return (
    <details
      className="study-note-management"
      open={!!form.state.pending || !!message || !!form.problem}
    >
      <summary>Gestionar esta nota</summary>
      <p>
        Estas acciones operan sobre la versión guardada. Los borradores locales,
        conceptos derivados y recursos compartidos se conservan.
      </p>
      <div className="study-actions">
        {family !== "diary" && (
          <button
            type="button"
            disabled={!note || busy || !!form.state.pending}
            onClick={() => select("duplicate")}
          >
            Duplicar nota completa
          </button>
        )}
        <button
          type="button"
          disabled={!note || busy || !!form.state.pending}
          onClick={() => select("delete")}
        >
          Eliminar nota guardada…
        </button>
      </div>
      {form.state.mode && (
        <fieldset disabled={busy || !!form.state.pending}>
          {form.state.mode === "duplicate" ? (
            <label>
              Título de la copia
              <input
                value={form.state.title}
                maxLength={500}
                onChange={(event) =>
                  form.set({ ...form.state, title: event.target.value })
                }
              />
            </label>
          ) : (
            <>
              <p>
                Se eliminará «{form.state.reviewTitle}» de esta biblioteca. Sus
                archivos físicos permanecen disponibles para otros documentos.
                Esta acción no borra tus borradores locales.
              </p>
              <label>
                Escribe el nombre de la nota para confirmar
                <input
                  value={form.state.typed}
                  onChange={(event) =>
                    form.set({ ...form.state, typed: event.target.value })
                  }
                />
              </label>
            </>
          )}
          <button
            type="button"
            disabled={
              !!form.problem ||
              !note ||
              note.revision !== form.state.revision ||
              (form.state.mode === "delete"
                ? form.state.typed !== form.state.reviewTitle
                : !form.state.title.trim())
            }
            onClick={() => void send()}
          >
            {form.state.mode === "duplicate"
              ? "Crear copia de esta nota"
              : "Confirmar eliminación de esta nota"}
          </button>
          <button
            type="button"
            onClick={() => form.set({ ...form.state, mode: "", typed: "" })}
          >
            Cancelar operación
          </button>
        </fieldset>
      )}
      {form.state.pending && (
        <div>
          <button
            type="button"
            disabled={busy || !!form.problem}
            onClick={() => void send()}
          >
            Reintentar la misma operación
          </button>
          <button type="button" onClick={form.download}>
            Descargar solicitud conservada
          </button>
        </div>
      )}
      {message && <p role="status">{message}</p>}
      {form.problem && (
        <p role="alert">
          {form.problem}
          <button type="button" onClick={form.download}>
            Descargar solicitud conservada
          </button>
        </p>
      )}
      <button type="button" disabled={busy} onClick={refresh}>
        Consultar versión actual de la nota
      </button>
      <button type="button" onClick={downloadDraft}>
        Descargar borrador local de esta nota
      </button>
    </details>
  );
}
