/** Document editing is local; only an explicit, durable intention publishes a note. */
import { useEffect, useMemo, useRef, useState } from "react";
import { createAdvancedReaderApi } from "../api/client";
import { intention } from "../knowledge-map/model";
import type { DocumentEditor } from "../knowledge-map/document-editor";
import { executeStudy, studyRequest } from "./api";
import type { NoteDetail, StudyContext } from "./api";
import { DocumentSurface } from "./DocumentSurface";
import type { StudyDraft } from "./drafts";
import { studyVault } from "./drafts";
import type { Navigate } from "./navigation";

export function NoteWorkspace({
  context,
  initialDraft,
  navigate,
  notify,
}: {
  context: StudyContext;
  initialDraft: StudyDraft;
  navigate: Navigate;
  notify: (message: string) => void;
}) {
  const draft = useRef<StudyDraft>(structuredClone(initialDraft));
  const [initial] = useState(() => ({
    content: initialDraft.content,
    snapshot: initialDraft.document,
  }));
  const [vault] = useState(() => studyVault(context.library_id));
  const readerApi = useMemo(
    () => createAdvancedReaderApi(context.library_id),
    [context.library_id],
  );
  const composer = useRef<DocumentEditor | null>(null),
    alive = useRef(true);
  const [title, setTitle] = useState(initialDraft.title),
    [status, setStatus] = useState("");
  const [pending, setPending] = useState(!!initialDraft.pending),
    [sending, setSending] = useState(false);
  const [stored, setStored] = useState(!!initialDraft.noteId);
  const [dirty, setDirty] = useState(false),
    [storageReady, setStorageReady] = useState(vault.available);
  useEffect(() => {
    alive.current = true;
    return () => {
      alive.current = false;
    };
  }, []);
  const keep = () => {
    vault.put(draft.current);
    if (alive.current) setStorageReady(vault.available);
  };
  const capture = () => {
    if (composer.current) {
      draft.current.content = composer.current.value();
      draft.current.document = composer.current.snapshot();
    }
    keep();
  };
  const submit = async (publish = false) => {
    if (sending) return;
    capture();
    if (!context.preparation.notes_ready) {
      setStatus(
        "Prepara notas y subrayados antes de guardar. El borrador se conserva.",
      );
      return;
    }
    if (!draft.current.pending) {
      if (!draft.current.title.trim() || !draft.current.content.trim()) {
        setStatus("Escribe un nombre y contenido para la nota.");
        return;
      }
      if (!composer.current?.valid()) {
        setStatus(
          "La fórmula está en elaboración. Borrador conservado; complétala antes de guardar.",
        );
        return;
      }
      if (publish && (!stored || dirty)) {
        setStatus(
          "Guarda primero los cambios de la nota y después incorpórala como concepto.",
        );
        return;
      }
      const value = {
        ...draft.current,
        action: publish ? ("publish_note" as const) : ("save_note" as const),
      };
      if (publish) value.noteRevision = value.revision;
      draft.current.pending = intention(value, crypto.randomUUID());
      if (draft.current.passage)
        draft.current.pending.annotation_id =
          draft.current.passage.annotation_id;
      keep(); // the same operation and passage IDs survive navigation, reload and lost replies
      if (!vault.available) {
        setStatus(
          "No se pudo conservar el identificador del envío. Descarga el borrador y recupera el almacenamiento antes de guardar.",
        );
        return;
      }
    }
    setPending(true);
    setSending(true);
    setStatus("Guardando… esperando confirmación de la biblioteca.");
    try {
      if (draft.current.passage && !stored)
        await readerApi.createVisualAnnotation(
          draft.current.documentId!,
          draft.current.passage,
        );
      const result = await executeStudy(context, draft.current.pending!);
      if (!alive.current) return;
      setStatus(result.message);
      if (["conflict", "invalid"].includes(result.status)) {
        draft.current.pending = undefined;
        setPending(false);
        keep();
      }
      if (!["saved", "duplicate"].includes(result.status)) return;
      if (result.note_id) {
        const note = await studyRequest<NoteDetail>(
          "/notes/" + encodeURIComponent(result.note_id),
          context,
        );
        if (!alive.current) return;
        draft.current.noteId = note.note_id;
        draft.current.revision = note.revision;
        draft.current.pending = undefined;
        draft.current.submitted = false;
        setPending(false);
        setStored(true);
        setDirty(false);
        keep();
        notify("Nota guardada. Tu texto está confirmado en esta biblioteca.");
        navigate("/study/notes/" + encodeURIComponent(note.note_id), true);
      } else if (result.key) {
        draft.current.pending = undefined;
        keep();
        notify(result.message);
        navigate("/study/concepts/" + encodeURIComponent(result.key));
      }
    } catch (reason) {
      if (alive.current)
        setStatus(
          (reason as Error).message +
            " El borrador y el mismo intento se conservan.",
        );
    } finally {
      if (alive.current) setSending(false);
    }
  };
  return (
    <section className="study-writing">
      <header>
        <p className="eyebrow">Cuaderno de lectura</p>
        <h1>{stored ? "Editar nota" : "Escribir nota"}</h1>
        <p>
          Una nota guardada sigue siendo tu nota. Incorporarla como concepto es
          una acción posterior.
        </p>
      </header>
      {!storageReady && (
        <p role="alert">
          Este navegador no pudo conservar el borrador. Descárgalo antes de
          cerrar.
        </p>
      )}
      {draft.current.passage && (
        <aside className="study-passage">
          <blockquote>{draft.current.passage.quote_text}</blockquote>
          <p>Pasaje de origen · página PDF {draft.current.passage.pdf_page}</p>
        </aside>
      )}
      <label>
        Nombre de la nota
        <input
          value={title}
          disabled={pending}
          maxLength={500}
          onChange={(event) => {
            setTitle(event.target.value);
            draft.current.title = event.target.value;
            setDirty(true);
            keep();
          }}
        />
      </label>
      <div className={pending ? "study-locked" : ""} inert={pending}>
        <DocumentSurface
          initial={initial.content}
          snapshot={initial.snapshot}
          editorRef={composer}
          changed={(content, snapshot) => {
            if (content !== draft.current.content) setDirty(true);
            draft.current.content = content;
            draft.current.document = snapshot;
            keep();
          }}
        />
      </div>
      <footer className="study-document-actions">
        <button
          className="primary-button"
          disabled={sending}
          onClick={() => void submit()}
        >
          {pending ? "Reintentar el mismo envío" : "Guardar nota"}
        </button>
        {stored && !pending && (
          <button disabled={dirty || sending} onClick={() => void submit(true)}>
            Incorporar como concepto
          </button>
        )}
        <button
          onClick={() => {
            capture();
            if (vault.available) {
              notify(
                "Borrador conservado en este navegador; no se publicó contenido nuevo.",
              );
              navigate("/study/notes");
            } else
              setStatus(
                "El borrador está sólo en memoria. Descárgalo antes de salir.",
              );
          }}
        >
          Conservar borrador y volver
        </button>
        <button
          onClick={() => {
            capture();
            const url = URL.createObjectURL(
              new Blob([JSON.stringify(draft.current)], {
                type: "application/json",
              }),
            );
            const link = document.createElement("a");
            link.href = url;
            link.download = "mathmongo-borrador.json";
            link.click();
            URL.revokeObjectURL(url);
          }}
        >
          Descargar borrador
        </button>
      </footer>
      <p role="status">
        {status ||
          (stored
            ? "Nota recuperada de la biblioteca."
            : "Borrador conservado en este navegador. Aún no es una nota guardada.")}
      </p>
      {draft.current.documentId && (
        <button
          onClick={() => {
            capture();
            navigate(
              "/study/read/" +
                encodeURIComponent(draft.current.documentId!) +
                (draft.current.passage
                  ? "?page=" + draft.current.passage.pdf_page
                  : ""),
            );
          }}
        >
          Volver al pasaje original
        </button>
      )}
    </section>
  );
}
