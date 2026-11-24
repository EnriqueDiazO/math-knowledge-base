/** Dedicated academic activities, with bounded metadata lists and on-demand bodies. */
import type { Page, StudyContext } from "./api";
import { useStudyResource, type Navigate } from "./navigation";
import { StudyLink } from "./StudyLink";
import { SavedNoteActions } from "./SavedNoteActions";
import { StructuredWorkspace } from "./StructuredWorkspace";
import type { Family, StructuredDetail } from "./structured-state";
export function StructuredPages({
  context,
  navigate,
  family,
  identity,
  search,
}: {
  context: StudyContext;
  navigate: Navigate;
  family: Family;
  identity: string;
  search: string;
}) {
  const title = family === "cornell" ? "Cornell" : "CPI";
  if (identity === "new")
    return (
      <StructuredWorkspace
        key={context.library_id + family}
        context={context}
        family={family}
        navigate={navigate}
      />
    );
  if (identity)
    return (
      <Saved
        key={context.library_id + identity}
        context={context}
        family={family}
        navigate={navigate}
        identity={identity}
      />
    );
  return (
    <Listing
      key={context.library_id + family + search}
      context={context}
      navigate={navigate}
      family={family}
      title={title}
      search={search}
    />
  );
}
function Saved({
  context,
  family,
  navigate,
  identity,
}: {
  context: StudyContext;
  family: Family;
  navigate: Navigate;
  identity: string;
}) {
  const resource = useStudyResource<StructuredDetail>(
    context,
    "/structured/" + family + "/" + encodeURIComponent(identity),
  );
  if (resource.error)
    return (
      <section>
        <p role="alert">
          {resource.error}
          <button onClick={resource.retry}>Reintentar nota</button>
          <StudyLink to={"/study/notebook/" + family} navigate={navigate}>
            Volver a la actividad
          </StudyLink>
        </p>
        <SavedNoteActions
          context={context}
          family={family}
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
        family={family}
        identity={identity}
        note={{
          title: resource.data.metadata.title || "Sin título",
          revision: resource.data.revision,
        }}
        navigate={navigate}
        refresh={resource.retry}
      />
      <StructuredWorkspace
        context={context}
        family={family}
        navigate={navigate}
        note={resource.data}
      />
    </section>
  ) : (
    <p role="status">Recuperando regiones y fuente original…</p>
  );
}
function Listing({
  context,
  navigate,
  family,
  title,
  search,
}: {
  context: StudyContext;
  navigate: Navigate;
  family: Family;
  title: string;
  search: string;
}) {
  const params = new URLSearchParams(search),
    page = Math.max(1, Number(params.get("page")) || 1),
    resource = useStudyResource<
      Page<{ note_id: string; title: string; date: string; project: string }>
    >(
      context,
      "/structured/" +
        family +
        "?" +
        new URLSearchParams({
          page: String(page),
          q: params.get("q") || "",
          project: params.get("project") || "",
          context: params.get("context") || "",
          ...(params.get("date_from")
            ? { date_from: params.get("date_from")! }
            : {}),
          ...(params.get("date_to") ? { date_to: params.get("date_to")! } : {}),
        }),
    ),
    root = "/study/notebook/" + family;
  return (
    <section>
      <StudyLink to="/study/notebook" navigate={navigate}>
        Volver a Cuaderno
      </StudyLink>
      <p className="eyebrow">Escritura académica por regiones</p>
      <h1>{title}</h1>
      <p>
        {family === "cornell"
          ? "Organiza preguntas, desarrollo y síntesis de tu estudio."
          : "Trabaja la comprensión, la producción y la integración de tus ideas."}
      </p>
      <StudyLink
        to={root + "/new"}
        navigate={navigate}
        className="primary-button"
      >
        + Nueva nota {title}
      </StudyLink>
      <form
        onSubmit={(event) => {
          event.preventDefault();
          params.set(
            "q",
            String(new FormData(event.currentTarget).get("q") || ""),
          );
          for (const key of ["project", "context", "date_from", "date_to"]) {
            const value = String(
              new FormData(event.currentTarget).get(key) || "",
            );
            if (value) params.set(key, value);
            else params.delete(key);
          }
          params.delete("page");
          navigate(root + "?" + params);
        }}
      >
        <label>
          Buscar notas {title}
          <input name="q" type="search" defaultValue={params.get("q") || ""} />
        </label>
        <details>
          <summary>Filtrar notas</summary>
          <label>
            Proyecto exacto
            <input name="project" defaultValue={params.get("project") || ""} />
          </label>
          <label>
            Contexto exacto
            <input name="context" defaultValue={params.get("context") || ""} />
          </label>
          <label>
            Desde la fecha
            <input
              name="date_from"
              type="date"
              defaultValue={params.get("date_from") || ""}
            />
          </label>
          <label>
            Hasta la fecha
            <input
              name="date_to"
              type="date"
              defaultValue={params.get("date_to") || ""}
            />
          </label>
        </details>
        <button type="submit">Buscar notas</button>
      </form>
      {resource.error && (
        <p role="alert">
          {resource.error}
          <button onClick={resource.retry}>Reintentar búsqueda</button>
        </p>
      )}
      {resource.data?.items.map((note) => (
        <article key={note.note_id}>
          <h2>
            <StudyLink
              to={root + "/" + encodeURIComponent(note.note_id)}
              navigate={navigate}
            >
              {note.title || "Nota sin título"}
            </StudyLink>
          </h2>
          <p>
            {note.date} · {note.project || "Sin proyecto"}
          </p>
        </article>
      ))}
      {resource.data?.total === 0 && (
        <p>
          Todavía no hay notas en esta búsqueda. Puedes crear una y recuperar su
          borrador aquí.
        </p>
      )}
      {resource.data && (
        <nav aria-label="Páginas de notas">
          <button
            disabled={page === 1}
            onClick={() => {
              params.set("page", String(page - 1));
              navigate(root + "?" + params);
            }}
          >
            Anteriores
          </button>
          <button
            disabled={page * 20 >= resource.data.total}
            onClick={() => {
              params.set("page", String(page + 1));
              navigate(root + "?" + params);
            }}
          >
            Siguientes
          </button>
        </nav>
      )}
    </section>
  );
}
