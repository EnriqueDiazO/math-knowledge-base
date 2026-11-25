/** A searchable library, two densities and contextual detail over the same canonical sources. */
import type { Page, SourceSummary, StudyContext } from "./api";
import { bibliographyLabel } from "./api";
import { useStudyResource, type Navigate } from "./navigation";
import { StudyLink } from "./StudyLink";
import { sourceTypes } from "./catalog-fields";
import { useInterfacePreferences } from "./interface-preferences";
import { bibliographicText } from "./bibliographic-text";
import { SourceSummaryPanel } from "./SourceSummaryPanel";
import "./library.css";
function SourceCard({
  source,
  navigate,
  selected,
  select,
}: {
  source: SourceSummary;
  navigate: Navigate;
  selected: boolean;
  select: () => void;
}) {
  const reference = source.bibliography?.[0],
    base = "/study/sources/" + encodeURIComponent(source.source_id);
  return (
    <article className="bibliographic-card" data-selected={selected}>
      <div className="source-kind">
        {sourceTypes[source.source_type as keyof typeof sourceTypes] ||
          source.source_type ||
          "Fuente"}
      </div>
      <div className="bibliographic-copy">
        <h2>
          <StudyLink to={base} navigate={navigate}>
            {bibliographicText(reference?.title || source.name)}
          </StudyLink>
        </h2>
        {reference?.title && reference.title !== source.name && (
          <p className="bibliographic-subtitle">
            Nombre histórico: {bibliographicText(source.name)}
          </p>
        )}
        <p className="bibliographic-authors">
          {bibliographicText(bibliographyLabel(reference)) ||
            "Sin autores o año registrados"}
        </p>
        {source.description && (
          <p className="bibliographic-description">
            {bibliographicText(source.description).slice(0, 280)}
          </p>
        )}
      </div>
      <div className="bibliographic-actions">
        <button
          aria-label={"Ver detalle de " + source.name}
          aria-pressed={selected}
          onClick={select}
        >
          Ver detalle
        </button>
        <StudyLink to={base} navigate={navigate}>
          Abrir fuente y documentos
        </StudyLink>
        <StudyLink to={base + "?section=edit-source"} navigate={navigate}>
          Editar
        </StudyLink>
      </div>
    </article>
  );
}
export function LibraryPage({
  context,
  navigate,
  search,
}: {
  context: StudyContext;
  navigate: Navigate;
  search: string;
}) {
  const { preferences, change } = useInterfacePreferences(),
    query = new URLSearchParams(search),
    q = query.get("q") ?? "",
    status = query.get("status") || "active",
    sourceType = query.get("type") || "",
    selected = query.get("selected") || "",
    page = Math.max(1, Number(query.get("page")) || 1);
  const filters = new URLSearchParams({ q, page: String(page) });
  if (status !== "active") filters.set("status", status);
  if (sourceType) filters.set("source_type", sourceType);
  const resource = useStudyResource<Page<SourceSummary>>(
    context,
    "/library?" + filters,
  );
  const select = (id: string) => {
    const next = new URLSearchParams(search);
    if (id) next.set("selected", id);
    else next.delete("selected");
    navigate("/study/library?" + next);
  };
  const adjacent = (number: number) =>
    "/study/library?" +
    new URLSearchParams({ q, status, type: sourceType, page: String(number) });
  return (
    <section className="study-library">
      <header className="page-heading">
        <div>
          <p className="eyebrow">Fuentes y biblioteca</p>
          <h1>Tu biblioteca</h1>
          {new URLSearchParams(search).get("activity") === "documents" && (
            <p>
              Elige una fuente y abre Documentos para adjuntar un PDF o
              continuar la lectura.
            </p>
          )}
          <p>Lecturas, referencias y documentos en un mismo lugar.</p>
        </div>
        <StudyLink
          to="/study/sources/new"
          navigate={navigate}
          className="primary-button"
        >
          + Añadir fuente
        </StudyLink>
      </header>
      <form
        className="study-search library-search"
        key={q + "|" + status + "|" + sourceType}
        onSubmit={(event) => {
          event.preventDefault();
          const form = new FormData(event.currentTarget),
            params = new URLSearchParams({
              q: String(form.get("query") || ""),
            });
          if (form.get("status") === "archived")
            params.set("status", "archived");
          if (form.get("type")) params.set("type", String(form.get("type")));
          navigate("/study/library?" + params);
        }}
      >
        <label>
          Buscar en la biblioteca
          <input
            name="query"
            defaultValue={q}
            maxLength={200}
            type="search"
            placeholder="Título, autor, año, DOI o ISBN"
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
      <div className="library-viewbar">
        <p aria-live="polite">
          {resource.data
            ? `${resource.data.total} fuentes encontradas`
            : "Consultando fuentes…"}
          {q && <> · «{q}»</>}
        </p>
        <div
          className="segmented-control"
          role="group"
          aria-label="Vista de biblioteca"
        >
          <button
            aria-pressed={preferences.libraryView === "cards"}
            onClick={() => change({ libraryView: "cards" })}
          >
            Fichas
          </button>
          <button
            aria-pressed={preferences.libraryView === "list"}
            onClick={() => change({ libraryView: "list" })}
          >
            Lista compacta
          </button>
        </div>
        <label className="density-select">
          Densidad
          <select
            value={preferences.density}
            onChange={(e) =>
              change({ density: e.target.value as "compact" | "comfortable" })
            }
          >
            <option value="comfortable">Cómoda</option>
            <option value="compact">Compacta</option>
          </select>
        </label>
      </div>
      {resource.error && (
        <p role="alert">
          {resource.error} <button onClick={resource.retry}>Reintentar</button>
        </p>
      )}
      <div className="library-workspace" data-detail={!!selected}>
        <div className="library-results">
          <div
            className="study-library-list"
            data-view={preferences.libraryView}
          >
            {resource.data?.items.map((source) => (
              <SourceCard
                key={source.source_id}
                source={source}
                navigate={navigate}
                selected={selected === source.source_id}
                select={() => select(source.source_id)}
              />
            ))}
          </div>
          {resource.data?.total === 0 && (
            <p>
              No hay fuentes para esta búsqueda. Cambia los términos para
              continuar.
            </p>
          )}
          <nav aria-label="Páginas de biblioteca">
            {page > 1 && (
              <StudyLink to={adjacent(page - 1)} navigate={navigate}>
                Anterior
              </StudyLink>
            )}
            {resource.data && page * 20 < resource.data.total && (
              <StudyLink to={adjacent(page + 1)} navigate={navigate}>
                Siguiente
              </StudyLink>
            )}
          </nav>
        </div>
        {selected && (
          <SourceSummaryPanel
            key={context.library_id + selected}
            context={context}
            identity={selected}
            navigate={navigate}
            close={() => select("")}
          />
        )}
      </div>
    </section>
  );
}
export { SourcePage } from "./SourcePage";
