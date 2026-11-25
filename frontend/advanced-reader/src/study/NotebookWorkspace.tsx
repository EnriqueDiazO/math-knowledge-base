/** Diario editing delegates documents, drafts, HTTP and exports to existing ports. */
import { useMemo, useRef, useState } from "react";
import type { DocumentEditor } from "../knowledge-map/document-editor";
import type { StudyContext } from "./api";
import { StudyApiError, studyRequest } from "./api";
import { DocumentContent, DocumentSurface } from "./DocumentSurface";
import { diaryDraftPrefix, type DiaryRestoration } from "./diary-storage";
import type { Navigate } from "./navigation";
import { StudyLink } from "./StudyLink";
import { useDiaryForm, useDiaryRestoration } from "./useDiaryForm";
import { useOperationScope } from "./useOperationScope";
import {
  diaryChanges,
  diaryDraft,
  diaryFields,
  diaryRebase,
  diarySnapshot,
  type DiaryDetail,
  type DiaryDraft,
} from "./notebook-state";
import { NotebookReferences } from "./NotebookReferences";
import { ExportActions } from "./ExportActions";

type Props = {
  context: StudyContext;
  note?: DiaryDetail;
  navigate: Navigate;
};

export function NotebookWorkspace(props: Props) {
  const key =
    diaryDraftPrefix(props.context.library_id) + (props.note?.note_id || "new");
  return <RestoringNotebook {...props} key={key} storageKey={key} />;
}

function RestoringNotebook(props: Props & { storageKey: string }) {
  const restored = useDiaryRestoration(props.storageKey);
  return restored ? (
    <NotebookEditor {...props} restored={restored} />
  ) : (
    <p role="status">Buscando un borrador del Cuaderno en este navegador…</p>
  );
}

function NotebookEditor({
  context,
  note,
  navigate,
  storageKey,
  restored: recovered,
}: Props & { storageKey: string; restored: DiaryRestoration }) {
  const form = useDiaryForm(storageKey, recovered, () => diaryDraft(note));
  const current = form.current,
    editor = useRef<DocumentEditor | null>(null),
    scope = useOperationScope(context);
  const finished = useRef(false),
    saving = useRef(false),
    surfaceEpoch = useRef(0);
  const [initial, setInitial] = useState(() => ({
    content: form.state.latex_body,
    snapshot: form.state.snapshot,
  }));
  const [epoch, setEpoch] = useState(0),
    [message, setMessage] = useState(""),
    [busy, setBusy] = useState(false),
    [conflict, setConflict] = useState(false),
    [remote, setRemote] = useState<DiaryDetail>();
  const remember = (next: DiaryDraft) =>
    finished.current ? Promise.resolve(true) : form.set(next);
  const update = (field: keyof DiaryDraft, value: string) =>
    remember({ ...current.current, [field]: value });
  const restored = useMemo(() => {
    try {
      return {
        snapshot: diarySnapshot({ snapshot: initial.snapshot }),
        problem: "",
      };
    } catch (error) {
      return { snapshot: undefined, problem: (error as Error).message };
    }
  }, [initial.snapshot]);
  let selected: string[] = [],
    problem = restored.problem;
  try {
    selected = diaryFields(form.state).catalog_reference_ids;
    diaryChanges(form.state);
    if (form.state.pending) JSON.parse(form.state.pending);
  } catch (error) {
    problem = (error as Error).message;
  }
  const blockingProblem = problem || form.problem;
  const path =
    "/notebook" + (note ? "/" + encodeURIComponent(note.note_id) : "");
  const save = async () => {
    if (busy || saving.current || blockingProblem || conflict) return;
    let draft = current.current;
    const prepare = !draft.pending;
    if (prepare) {
      if (!editor.current?.valid()) {
        setMessage(
          "Completa la fórmula antes de guardar. El borrador se conserva.",
        );
        return;
      }
      draft = {
        ...draft,
        latex_body: editor.current.value(),
        snapshot: JSON.stringify(editor.current.snapshot()),
      };
      if (
        !draft.title.trim() ||
        !draft.latex_body.trim() ||
        (!note && !draft.date)
      ) {
        setMessage(
          "Escribe título, fecha y contenido. El borrador se conserva.",
        );
        return;
      }
      const payload = note
        ? { revision: draft.revision, changes: diaryChanges(draft) }
        : { request_id: draft.request_id, ...diaryFields(draft) };
      draft = { ...draft, pending: JSON.stringify(payload) };
    }
    saving.current = true;
    setBusy(true);
    try {
      if (prepare && !(await remember(draft))) {
        // This attempt was never sent. Keep the document editable and retry persistence later.
        if (scope.active) {
          form.keep({ ...draft, pending: "" });
          setMessage(
            "No se envió la entrada. El borrador sigue abierto en esta pestaña.",
          );
        }
        return;
      }
      if (!scope.active) return;
      setMessage("Guardando entrada… esperando confirmación de la biblioteca.");
      const body = JSON.parse(draft.pending),
        result = await studyRequest<DiaryDetail>(path, context, body);
      if (!scope.active) return;
      const expected = note ? body.changes : diaryFields(draft);
      const confirmed = {
        ...result,
        catalog_reference_ids: result.references
          .map((item) => item.catalog_reference_id)
          .filter(Boolean),
      };
      if (
        Object.entries(expected).some(
          ([key, value]) =>
            JSON.stringify(confirmed[key as keyof typeof confirmed]) !==
            JSON.stringify(value),
        )
      )
        throw new Error(
          "No se confirmó el contenido guardado. El borrador y el intento se conservan para reintentar.",
        );
      if (!note) {
        finished.current = true;
        await form.clear();
        if (scope.active)
          navigate("/study/notebook/" + encodeURIComponent(result.note_id));
        return;
      }
      void remember({ ...diaryDraft(result), snapshot: draft.snapshot });
      setMessage("Entrada guardada y confirmada en esta biblioteca.");
    } catch (error) {
      if (!scope.active) return;
      if (
        error instanceof StudyApiError &&
        ["catalog_conflict", "invalid_study_request"].includes(error.code)
      ) {
        void remember({ ...current.current, pending: "" });
        setConflict(!!note && error.code === "catalog_conflict");
      }
      setMessage((error as Error).message);
    } finally {
      saving.current = false;
      if (scope.active) setBusy(false);
    }
  };
  const review = async () => {
    try {
      const value = await studyRequest<DiaryDetail>(path, context);
      if (scope.active) setRemote(value);
    } catch (error) {
      if (scope.active) setMessage((error as Error).message);
    }
  };
  const restart = async () => {
    setBusy(true);
    const next = diaryDraft(note);
    const archived = await form.restart(next);
    if (!scope.active) return;
    if (archived) {
      surfaceEpoch.current = epoch + 1;
      setInitial({ content: next.latex_body, snapshot: next.snapshot });
      setEpoch(epoch + 1);
      setConflict(false);
      setRemote(undefined);
    }
    setMessage(
      archived
        ? ""
        : "No se pudo conservar la copia. El borrador original sigue intacto.",
    );
    setBusy(false);
  };
  const retry = async () => {
    if ((await form.retry()) && scope.active) setMessage("");
  };
  return (
    <section>
      <StudyLink to="/study/notebook" navigate={navigate}>
        Volver a Cuaderno
      </StudyLink>
      <p className="eyebrow">Diario · LaTeX canónico</p>
      <h1>
        {note ? "Editar entrada del Cuaderno" : "Nueva entrada del Cuaderno"}
      </h1>
      <p role="status">
        {message ||
          (!form.storageFailed &&
            !blockingProblem &&
            "El borrador se conserva en este navegador; guardarlo lo confirma en la biblioteca.")}
      </p>
      {blockingProblem && (
        <div role="alert">
          {blockingProblem}
          <div className="study-actions">
            <button onClick={form.download}>Descargar borrador</button>
            <button disabled={busy} onClick={() => void restart()}>
              Reiniciar con copia
            </button>
          </div>
        </div>
      )}
      {form.storageFailed && !blockingProblem && (
        <div role="alert">
          El navegador no pudo conservar el borrador. Puedes seguir editando en
          esta pestaña. Descarga una copia antes de salir o recargar.
          <div className="study-actions">
            <button onClick={form.download}>Descargar borrador</button>
            <button disabled={busy} onClick={() => void retry()}>
              Reintentar conservar borrador
            </button>
          </div>
        </div>
      )}
      <fieldset
        disabled={
          busy || !!form.state.pending || conflict || !!blockingProblem
        }
      >
        <label>
          Título de la entrada
          <input
            value={form.state.title}
            onChange={(event) => update("title", event.target.value)}
          />
        </label>
        <details>
          <summary>Fecha, proyecto y etiquetas</summary>
          <label>
            Fecha de la entrada
            <input
              type="date"
              value={form.state.date}
              onChange={(event) => update("date", event.target.value)}
            />
          </label>
          <label>
            Proyecto
            <input
              value={form.state.project}
              onChange={(event) => update("project", event.target.value)}
            />
          </label>
          <label>
            Contexto
            <input
              value={form.state.context}
              onChange={(event) => update("context", event.target.value)}
            />
          </label>
          <label>
            Etiquetas (una por línea)
            <textarea
              value={form.state.tags}
              onChange={(event) => update("tags", event.target.value)}
            />
          </label>
        </details>
        <NotebookReferences
          context={context}
          selected={selected}
          existing={note?.references || []}
          changed={(ids) => update("references", JSON.stringify(ids))}
        />
      </fieldset>
      {!blockingProblem && (
        <div inert={busy || !!form.state.pending || conflict}>
          <DocumentSurface
            key={epoch}
            initial={initial.content}
            snapshot={restored.snapshot}
            context={context}
            title={form.state.title}
            editorRef={editor}
            changed={(latex, state) => {
              if (
                epoch !== surfaceEpoch.current ||
                saving.current ||
                current.current.pending
              )
                return;
              const snapshot = JSON.stringify(state);
              if (
                latex !== current.current.latex_body ||
                snapshot !== current.current.snapshot
              )
                void remember({
                  ...current.current,
                  latex_body: latex,
                  snapshot,
                });
            }}
          />
        </div>
      )}
      <div className="study-actions">
        <button
          className="primary-button"
          disabled={busy || conflict || !!blockingProblem}
          onClick={() => void save()}
        >
          {form.state.pending
            ? "Reintentar el mismo guardado"
            : "Guardar entrada"}
        </button>
        {!blockingProblem && !form.storageFailed && (
          <button onClick={form.download}>Descargar borrador</button>
        )}
      </div>
      {note && <ExportActions context={context} notebookId={note.note_id} />}
      {conflict && (
        <aside>
          <p>
            Tu escritura sigue aquí. Consulta la versión guardada antes de
            combinar explícitamente tus cambios.
          </p>
          <button onClick={() => void review()}>
            Consultar versión guardada
          </button>
          {remote && (
            <>
              <h2>Versión guardada: {remote.title}</h2>
              <DocumentContent content={remote.latex_body} context={context} />
              <button
                onClick={() => {
                  const next = diaryRebase(current.current, remote);
                  surfaceEpoch.current = epoch + 1;
                  remember(next);
                  setInitial({
                    content: next.latex_body,
                    snapshot: next.snapshot,
                  });
                  setEpoch(epoch + 1);
                  setConflict(false);
                  setRemote(undefined);
                  setMessage(
                    "Se conservaron tus campos modificados sobre la versión consultada. Revisa y guarda explícitamente.",
                  );
                }}
              >
                Continuar sobre esta versión
              </button>
            </>
          )}
        </aside>
      )}
      {note?.image_count ? (
        <p>
          Se conservan {note.image_count} asociaciones de medios existentes. Su
          administración completa sigue pendiente de migración.
        </p>
      ) : null}
    </section>
  );
}
