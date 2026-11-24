/** Bounded Diario navigation; full LaTeX is opened only in the shared workspace. */
import type { Page, StudyContext } from "./api";
import type { DiaryDetail } from "./notebook-state";
import type { Navigate } from "./navigation";
import { useStudyResource } from "./navigation";
import { StudyLink } from "./StudyLink";
import { NotebookWorkspace } from "./NotebookWorkspace";
export function NotebookPages({
  context,
  navigate,
  identity,
  search,
}: {
  context: StudyContext;
  navigate: Navigate;
  identity: string;
  search: string;
}) {
  if (identity === "new")
    return (
      <NotebookWorkspace
        key={context.library_id + identity}
        context={context}
        navigate={navigate}
      />
    );
  return identity ? (
    <SavedEntry
      key={context.library_id + identity}
      context={context}
      navigate={navigate}
      identity={identity}
    />
  ) : (
    <DiaryList
      key={search}
      context={context}
      navigate={navigate}
      search={search}
    />
  );
}
function SavedEntry({
  context,
  navigate,
  identity,
}: {
  context: StudyContext;
  navigate: Navigate;
  identity: string;
}) {
  const resource = useStudyResource<DiaryDetail>(
    context,
    "/notebook/" + encodeURIComponent(identity),
  );
  if (resource.error)
    return (
      <p role="alert">
        {resource.error}
        <button onClick={resource.retry}>Reintentar entrada</button>
        <StudyLink to="/study/notebook" navigate={navigate}>
          Volver a Cuaderno
        </StudyLink>
      </p>
    );
  return resource.data ? (
    <NotebookWorkspace
      context={context}
      navigate={navigate}
      note={resource.data}
    />
  ) : (
    <p role="status">Recuperando la entrada del Cuaderno…</p>
  );
}
function DiaryList({
  context,
  navigate,
  search,
}: {
  context: StudyContext;
  navigate: Navigate;
  search: string;
}) {
  const params = new URLSearchParams(search),
    page = Math.max(1, Number(params.get("page")) || 1);
  const resource = useStudyResource<Page<DiaryDetail>>(
    context,
    "/notebook?" +
      new URLSearchParams({
        page: String(page),
        q: params.get("q") || "",
        project: params.get("project") || "",
        source_id: params.get("source") || "",
      }),
  );
  const change = (next: number) => {
    params.set("page", String(next));
    navigate("/study/notebook?" + params);
  };
  return (
    <section>
      <p className="eyebrow">Escritura por fecha y proyecto</p>
      <h1>Cuaderno</h1>
      <StudyLink
        to="/study/notebook/new"
        navigate={navigate}
        className="primary-button"
      >
        + Nueva entrada
      </StudyLink>
      <form
        onSubmit={(event) => {
          event.preventDefault();
          const values = new FormData(event.currentTarget);
          params.set("q", String(values.get("q") || ""));
          params.set("project", String(values.get("project") || ""));
          params.delete("page");
          navigate("/study/notebook?" + params);
        }}
      >
        <label>
          Buscar en el Cuaderno
          <input type="search" name="q" defaultValue={params.get("q") || ""} />
        </label>
        <label>
          Filtrar por proyecto
          <input name="project" defaultValue={params.get("project") || ""} />
        </label>
        <button>Buscar entradas</button>
      </form>
      {resource.error && (
        <p role="alert">
          {resource.error}
          <button onClick={resource.retry}>Reintentar Cuaderno</button>
        </p>
      )}
      {resource.data?.items.map((note) => (
        <article key={note.note_id}>
          <h2>
            <StudyLink
              to={"/study/notebook/" + encodeURIComponent(note.note_id)}
              navigate={navigate}
            >
              {note.title || "Entrada sin título"}
            </StudyLink>
          </h2>
          <p>
            {note.date} · {note.project || "Sin proyecto"} ·{" "}
            {note.context || "Sin contexto"}
          </p>
        </article>
      ))}
      {resource.data && !resource.data.items.length && (
        <p>
          No hay entradas de Diario para esta búsqueda. Puedes crear una o
          recuperar un borrador.
        </p>
      )}
      <StudyLink to="/study/notebook/new" navigate={navigate}>
        Recuperar borrador de entrada nueva
      </StudyLink>
      {resource.data && (
        <nav aria-label="Páginas del Cuaderno">
          <button disabled={page === 1} onClick={() => change(page - 1)}>
            Entradas anteriores
          </button>
          <button
            disabled={page * 20 >= resource.data.total}
            onClick={() => change(page + 1)}
          >
            Más entradas
          </button>
        </nav>
      )}
      <details>
        <summary>Otras actividades del Cuaderno</summary>
        <p>
          Cornell, CPI, Worklog, Backlog, revisiones semanales y entregables
          conservan sus modelos. Sus operaciones completas siguen pendientes de
          migración; estas entradas de Diario no las sustituyen.
        </p>
      </details>
    </section>
  );
}
