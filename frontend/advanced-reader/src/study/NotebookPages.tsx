/** Bounded Diario navigation; full LaTeX is opened only in the shared workspace. */
import type { Page, StudyContext } from "./api";
import type { DiaryDetail } from "./notebook-state";
import type { Navigate } from "./navigation";
import { useStudyResource } from "./navigation";
import { StudyLink } from "./StudyLink";
import { SavedNoteActions } from "./SavedNoteActions";
import { NotebookWorkspace } from "./NotebookWorkspace";
import { DiaryNavigation, DiaryFilters } from "./DiaryNavigation";
import "./notebook-activities.css";
import { NotebookNavigation } from "./NotebookNavigation";
import { ActivityPages } from "./ActivityPages";
import type { ActivityKind } from "./activity-fields";
import { lazy } from "react";
const StructuredPages = lazy(() =>
  import("./StructuredPages").then((module) => ({
    default: module.StructuredPages,
  })),
);
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
  const [family, ...rest] = identity.split("/");
  if (
    ["worklog", "backlog", "weekly", "deliverables", "kanban"].includes(family)
  )
    return (
      <ActivityPages
        key={context.library_id + identity}
        context={context}
        navigate={navigate}
        kind={(family === "kanban" ? "backlog" : family) as ActivityKind}
        identity={rest.join("/")}
        search={search}
        kanban={family === "kanban"}
      />
    );
  if (family === "cornell" || family === "cpi")
    return (
      <StructuredPages
        context={context}
        navigate={navigate}
        family={family}
        identity={rest.join("/")}
        search={search}
      />
    );
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
      <section>
        <p role="alert">
          {resource.error}
          <button onClick={resource.retry}>Reintentar entrada</button>
          <StudyLink to="/study/notebook" navigate={navigate}>
            Volver a Cuaderno
          </StudyLink>
        </p>
        <SavedNoteActions
          context={context}
          family="diary"
          identity={identity}
          navigate={navigate}
          refresh={resource.retry}
        />
      </section>
    );
  return resource.data ? (
    <section>
      <SavedNoteActions
        context={context}
        family="diary"
        identity={identity}
        note={{
          title: resource.data.title || "Sin título",
          revision: resource.data.revision,
        }}
        navigate={navigate}
        refresh={resource.retry}
      />
      <NotebookWorkspace
        context={context}
        navigate={navigate}
        note={resource.data}
      />
    </section>
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
    page = Math.max(1, Number(params.get("page")) || 1),
    view = params.get("view") || "search";
  const filters = Object.fromEntries(
    [
      "context",
      "tags",
      "start_date",
      "end_date",
      "year",
      "month",
      "updated_recently",
    ]
      .filter((key) => params.get(key))
      .map((key) => [key, params.get(key)!]),
  );
  const resource = useStudyResource<Page<DiaryDetail>>(
    context,
    "/notebook?" +
      new URLSearchParams({
        ...filters,
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
      <p>Diario LaTeX · entradas recuperables</p>
      <NotebookNavigation navigate={navigate} />
      <DiaryNavigation navigate={navigate} />
      {view === "timeline" && <h2>Timeline · entradas por fecha</h2>}
      {view === "calendar" && (
        <>
          <h2>Calendario</h2>
          <p>
            Elige año y mes para localizar las notas por fecha. La lista
            mantiene la paginación del Diario.
          </p>
        </>
      )}
      {view === "projects" && (
        <>
          <h2>Proyectos</h2>
          <p>
            Filtra por el nombre del proyecto para abrir sus notas, conservando
            sus asociaciones.
          </p>
        </>
      )}
      {view === "export" && (
        <>
          <h2>Exportar Diario</h2>
          <p>
            Abre una entrada y utiliza Descargar TEX o Exportar PDF. La
            exportación conjunta de varias notas sigue pendiente.
          </p>
        </>
      )}
      <nav aria-label="Actividades de estudio">
        <StudyLink to="/study/notebook/cornell" navigate={navigate}>
          Cornell
        </StudyLink>
        <StudyLink to="/study/notebook/cpi" navigate={navigate}>
          CPI
        </StudyLink>
      </nav>
      <StudyLink
        to="/study/notebook/new"
        navigate={navigate}
        className="primary-button"
      >
        + Nueva entrada
      </StudyLink>
      <DiaryFilters search={search} navigate={navigate} />
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
        <summary>Promover y otras operaciones pendientes</summary>
        <p>
          Worklog, Backlog, revisiones semanales, entregables y Kanban tienen
          accesos propios arriba. Las operaciones todavía no verificadas se
          registran en la matriz de migración; Diario, Cornell y CPI no las
          sustituyen.
        </p>
      </details>
    </section>
  );
}
