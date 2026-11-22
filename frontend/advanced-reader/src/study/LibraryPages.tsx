import { useState } from "react";
import type { Page, SourceDetail, SourceSummary, StudyContext } from "./api";
import { bibliographyLabel } from "./api";
import { useStudyResource } from "./navigation";
import { StudyLink } from "./StudyLink";
import type { Navigate } from "./navigation";

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
    q = query.get("q") ?? "";
  const page = Math.max(1, Number(query.get("page")) || 1);
  const resource = useStudyResource<Page<SourceSummary>>(
    context,
    "/library?" + new URLSearchParams({ q, page: String(page) }),
  );
  return (
    <section>
      <header>
        <p className="eyebrow">Fuentes y biblioteca</p>
        <h1>Tu biblioteca</h1>
        <p>Localiza una lectura por título, autor, año, DOI o ISBN.</p>
      </header>
      <form
        className="study-search"
        onSubmit={(event) => {
          event.preventDefault();
          const value = new FormData(event.currentTarget).get(
            "query",
          ) as string;
          navigate("/study/library?" + new URLSearchParams({ q: value }));
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
        <button>Buscar</button>
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
                  new URLSearchParams({ q, page: String(page - 1) })
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
                  new URLSearchParams({ q, page: String(page + 1) })
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
export function SourcePage({
  context,
  sourceId,
  navigate,
}: {
  context: StudyContext;
  sourceId: string;
  navigate: Navigate;
}) {
  const resource = useStudyResource<SourceDetail>(
    context,
    "/sources/" + encodeURIComponent(sourceId),
  );
  const [section, setSection] = useState("documents");
  if (resource.error)
    return (
      <p role="alert">
        {resource.error} <button onClick={resource.retry}>Reintentar</button>
      </p>
    );
  const source = resource.data;
  if (!source) return <p role="status">Abriendo la fuente…</p>;
  return (
    <section>
      <StudyLink to="/study/library" navigate={navigate}>
        Volver a Biblioteca
      </StudyLink>
      <header>
        <p className="eyebrow">Fuente de estudio</p>
        <h1>{source.name}</h1>
        <p>{source.description}</p>
      </header>
      <div className="study-actions">
        <button
          onClick={() => setSection("documents")}
          aria-pressed={section === "documents"}
        >
          Documentos
        </button>
        <button
          onClick={() => setSection("references")}
          aria-pressed={section === "references"}
        >
          Bibliografía
        </button>
        <StudyLink
          to={"/study/write?source=" + encodeURIComponent(sourceId)}
          navigate={navigate}
        >
          Escribir nota sobre esta fuente
        </StudyLink>
      </div>
      {section === "documents" ? (
        <div className="study-library-list">
          {source.documents.map((document) => (
            <article key={document.document_id}>
              <h2>{document.title}</h2>
              <p>{document.kind === "pdf" ? "Documento PDF" : "Página web"}</p>
              <StudyLink
                to={"/study/read/" + encodeURIComponent(document.document_id)}
                navigate={navigate}
              >
                Leer documento
              </StudyLink>
            </article>
          ))}
          {!source.documents.length && (
            <p>
              Esta fuente aún no tiene documentos. Puedes escribir una nota
              sobre ella.
            </p>
          )}
        </div>
      ) : (
        <section aria-label="Bibliografía">
          {source.references.map((reference, index) => (
            <article key={index}>
              <h2>{reference.title || source.name}</h2>
              <p>{bibliographyLabel(reference)}</p>
              {reference.doi && <p>DOI: {reference.doi}</p>}
              {reference.isbn?.length ? (
                <p>ISBN: {reference.isbn.join(", ")}</p>
              ) : null}
            </article>
          ))}
          {!source.references.length && (
            <p>
              Esta fuente todavía no tiene una referencia bibliográfica
              asociada.
            </p>
          )}
        </section>
      )}
    </section>
  );
}
