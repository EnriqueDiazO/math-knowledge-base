import { useEffect, useMemo } from "react";
import type { NoteDetail, Page, StudyContext } from "./api";
import { newStudyDraft, noteDraft, studyVault } from "./drafts";
import type { StudyDraft } from "./drafts";
import { useStudyResource } from "./navigation";
import { StudyLink } from "./StudyLink";
import type { Navigate } from "./navigation";
import { NoteWorkspace } from "./NoteWorkspace";

export function NotesPage({
  context,
  navigate,
  search = "",
}: {
  context: StudyContext;
  navigate: Navigate;
  search?: string;
}) {
  const params=new URLSearchParams(search),q=params.get("q")||"",page=Math.max(1,Number(params.get("page"))||1);
  const resource = useStudyResource<Page<NoteDetail>>(context, "/notes?"+new URLSearchParams({q,page:String(page),source_id:params.get("source")||"",document_id:params.get("document")||""}));
  const changePage=(next:number)=>{params.set("page",String(next));navigate("/study/notes?"+params);};
  const vault = useMemo(
    () => studyVault(context.library_id),
    [context.library_id],
  );
  const drafts = vault.all();
  return (
    <section>
      <header>
        <p className="eyebrow">Escritura y recuperación</p>
        <h1>Notas</h1>
        <StudyLink to="/study/write" navigate={navigate} className="primary-button">
          + Crear nota
        </StudyLink>
      </header>
      <form onSubmit={event=>{event.preventDefault();params.set("q",String(new FormData(event.currentTarget).get("q")||""));params.delete("page");navigate("/study/notes?"+params);}}>
        <label>Buscar notas por título<input type="search" name="q" key={q} defaultValue={q}/></label>
        <button type="submit">Buscar notas</button>
      </form>
      {drafts.length > 0 && (
        <section>
          <h2>Continuar escritura local</h2>
          <ul>
            {drafts.map((draft) => (
              <li key={draft.id}>
                <StudyLink
                  to={"/study/write?draft=" + encodeURIComponent(draft.id!)}
                  navigate={navigate}
                >
                  {draft.title || "Borrador sin nombre"}
                </StudyLink>
                <span>
                  {" "}
                  ·{" "}
                  {draft.noteId
                    ? "con nota guardada en la biblioteca"
                    : "borrador sin publicar"}
                </span>
              </li>
            ))}
          </ul>
        </section>
      )}
      <h2>Notas guardadas</h2>
      {resource.error && (
        <p role="alert">
          {resource.error} <button onClick={resource.retry}>Reintentar</button>
        </p>
      )}
      {resource.data?.items.map((note) => (
        <article key={note.note_id}>
          <h3>
            <StudyLink
              to={"/study/notes/" + encodeURIComponent(note.note_id)}
              navigate={navigate}
            >
              {note.title}
            </StudyLink>
          </h3>
          <p>Nota confirmada en esta biblioteca</p>
        </article>
      ))}
      {resource.data && !resource.data.items.length && (
        <p>Tus notas aparecerán aquí después de guardarlas.</p>
      )}
      {resource.data&&<nav aria-label="Páginas de notas"><button disabled={page===1} onClick={()=>changePage(page-1)}>Notas anteriores</button><span>Página {page}</span><button disabled={page*20>=resource.data.total} onClick={()=>changePage(page+1)}>Más notas</button></nav>}
    </section>
  );
}
export function WritePage({
  context,
  navigate,
  search,
  notify,
}: {
  context: StudyContext;
  navigate: Navigate;
  search: string;
  notify: (message: string) => void;
}) {
  const draft = useMemo(() => {
    const parameters = new URLSearchParams(search),
      vault = studyVault(context.library_id);
    const selected = parameters.get("draft");
    if (selected) {
      const recovered=vault.get(selected) as StudyDraft | undefined;
      if(recovered&&!recovered.noteId&&!recovered.pending&&parameters.get("source")){
        recovered.source=parameters.get("source")!;vault.put(recovered);
      }
      return recovered;
    }
    const source = parameters.get("source");
    const created = newStudyDraft(source||"");
    vault.put(created);
    return created;
  }, [search, context.library_id]);
  useEffect(() => {
    if (draft && !new URLSearchParams(search).has("draft"))
      navigate("/study/write?draft=" + encodeURIComponent(draft.id!), true);
  }, [draft, search, navigate]);
  if (!draft)
    return (
      <section>
        <h1>Crear nota</h1>
        <p>Elige una fuente en Biblioteca o recupera un borrador de Notas.</p>
        <StudyLink to="/study/library" navigate={navigate}>
          Abrir Biblioteca
        </StudyLink>
      </section>
    );
  return (
    <NoteWorkspace
      key={context.library_id + draft.id}
      context={context}
      initialDraft={draft}
      navigate={navigate}
      notify={notify}
    />
  );
}
export function SavedNotePage({
  context,
  noteId,
  navigate,
  notify,
  preferSaved = false,
}: {
  context: StudyContext;
  noteId: string;
  navigate: Navigate;
  notify: (message: string) => void;
  preferSaved?: boolean;
}) {
  const resource = useStudyResource<NoteDetail>(
    context,
    "/notes/" + encodeURIComponent(noteId),
  );
  const draft = useMemo(() => {
    if (!resource.data) return;
    const vault = studyVault(context.library_id);
    const existing = vault.all().find((item) => item.noteId === noteId) as
      | StudyDraft
      | undefined;
    return (!preferSaved && existing) || noteDraft(resource.data);
  }, [resource.data, context.library_id, noteId, preferSaved]);
  if (resource.error)
    return (
      <p role="alert">
        {resource.error} <button onClick={resource.retry}>Reintentar</button>
      </p>
    );
  if (!draft) return <p role="status">Recuperando la nota guardada…</p>;
  return (
    <NoteWorkspace
      key={context.library_id + noteId + preferSaved}
      context={context}
      initialDraft={draft}
      navigate={navigate}
      notify={notify}
    />
  );
}
