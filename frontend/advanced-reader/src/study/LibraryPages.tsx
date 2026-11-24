import type { Page, SourceSummary, StudyContext } from "./api";
import { bibliographyLabel } from "./api";
import { useStudyResource } from "./navigation";
import { StudyLink } from "./StudyLink";
import type { Navigate } from "./navigation";
import { sourceTypes } from "./catalog-fields";

export function LibraryPage({
  context,
  navigate,
  search,
}: {
  context: StudyContext;
  navigate: Navigate;
  search: string;
}) {
  const query = new URLSearchParams(search),
    q = query.get("q") ?? "",
    status = query.get("status") || "active",
    sourceType = query.get("type") || "";
  const page = Math.max(1, Number(query.get("page")) || 1);
  const filters = new URLSearchParams({q,page:String(page)});
  if (status !== "active") filters.set("status",status);
  if (sourceType) filters.set("source_type",sourceType);
  const resource = useStudyResource<Page<SourceSummary>>(context, "/library?" + filters);
  return (
    <section>
      <header>
        <p className="eyebrow">Fuentes y biblioteca</p>
        <h1>Tu biblioteca</h1>
        <p>Localiza una lectura por título, autor, año, DOI o ISBN.</p>
        <StudyLink
          to="/study/sources/new"
          navigate={navigate}
          className="primary-button"
        >
          + Añadir fuente
        </StudyLink>
      </header>
      <form
        className="study-search"
        onSubmit={(event) => {
          event.preventDefault();
          const value = new FormData(event.currentTarget).get(
            "query",
          ) as string;
          const form = new FormData(event.currentTarget);
          const params = new URLSearchParams({q:value});
          if (form.get("status") === "archived") params.set("status", "archived");
          if (form.get("type")) params.set("type", String(form.get("type")));
          navigate("/study/library?" + params);
        }}
      >
        <label>
          Buscar en la biblioteca
          <input
            key={q}
            name="query"
            defaultValue={q}
            maxLength={200}
            type="search"
          />
        </label>
        <label>
          Tipo de fuente
          <select name="type" defaultValue={sourceType}>
            <option value="">Todos los tipos</option>
            {Object.entries(sourceTypes).map(([value, label]) => (
              <option value={value} key={value}>
                {label}
              </option>
            ))}
          </select>
        </label>
        <label>
          Estado de las fuentes
          <select name="status" defaultValue={status}>
            <option value="active">Activas</option>
            <option value="archived">Archivadas</option>
          </select>
        </label>
        <button type="submit">Buscar</button>
      </form>
      {resource.error && (
        <p role="alert">
          {resource.error} <button onClick={resource.retry}>Reintentar</button>
        </p>
      )}
      {!resource.data && !resource.error && (
        <p role="status">Abriendo la biblioteca…</p>
      )}
      {resource.data && (
        <>
          <p>{resource.data.total} fuentes encontradas</p>
          <div className="study-library-list">
            {resource.data.items.map((source) => (
              <article key={source.source_id}>
                <h2>
                  <StudyLink
                    to={
                      "/study/sources/" + encodeURIComponent(source.source_id)
                    }
                    navigate={navigate}
                  >
                    {source.name}
                  </StudyLink>
                </h2>
                <p>{bibliographyLabel(source.bibliography?.[0])}</p>
                {source.description && (
                  <p>{source.description.slice(0, 260)}</p>
                )}
                <StudyLink
                  to={"/study/sources/" + encodeURIComponent(source.source_id)}
                  navigate={navigate}
                >
                  Abrir fuente y documentos
                </StudyLink>
              </article>
            ))}
          </div>
          <nav aria-label="Páginas de biblioteca">
            {page > 1 && (
              <StudyLink
                to={
                  "/study/library?" +
                  new URLSearchParams({
                    q,
                    status,
                    type: sourceType,
                    page: String(page - 1),
                  })
                }
                navigate={navigate}
              >
                Anterior
              </StudyLink>
            )}
            {page * 20 < resource.data.total && (
              <StudyLink
                to={
                  "/study/library?" +
                  new URLSearchParams({
                    q,
                    status,
                    type: sourceType,
                    page: String(page + 1),
                  })
                }
                navigate={navigate}
              >
                Siguiente
              </StudyLink>
            )}
          </nav>
          {!resource.data.total && (
            <p>
              No hay fuentes para esta búsqueda. Cambia los términos para
              continuar.
            </p>
          )}
        </>
      )}
    </section>
  );
}
export { SourcePage } from "./SourcePage";
