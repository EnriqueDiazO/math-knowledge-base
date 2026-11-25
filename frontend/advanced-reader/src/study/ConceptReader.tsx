/** Read the original concept, with its existing edit/export/relations flows and optional context. */
import type { ConceptDetail, StudyContext } from "./api";
import { useStudyResource, type Navigate } from "./navigation";
import { StudyLink } from "./StudyLink";
import { DocumentContent } from "./DocumentSurface";
import { ConceptTypeBadge } from "./ConceptTypeBadge";
import { ExportActions } from "./ExportActions";
import { ConceptRelations } from "./ConceptRelations";
import { useInterfacePreferences } from "./interface-preferences";
import { bibliographicText } from "./bibliographic-text";
import "./concept-reader.css";
export function ConceptPage({
  context,
  conceptKey,
  navigate,
}: {
  context: StudyContext;
  conceptKey: string;
  navigate: Navigate;
}) {
  const resource = useStudyResource<ConceptDetail>(
      context,
      "/concepts/detail?" + new URLSearchParams({ key: conceptKey }),
    ),
    { preferences, change } = useInterfacePreferences();
  if (resource.error)
    return (
      <p role="alert">
        {resource.error} <button onClick={resource.retry}>Reintentar</button>
      </p>
    );
  const concept = resource.data;
  if (!concept) return <p role="status">Abriendo el concepto…</p>;
  const reference = concept.reference || {};
  return (
    <section className="concept-reader">
      <nav aria-label="Ruta del concepto">
        <StudyLink to="/study/concepts" navigate={navigate}>
          Volver a Conceptos
        </StudyLink>
        <span aria-hidden="true"> / </span>
        <span>{bibliographicText(concept.titulo)}</span>
      </nav>
      <header className="concept-heading">
        <div>
          <p className="eyebrow">
            <ConceptTypeBadge type={concept.tipo} />
          </p>
          <h1>{bibliographicText(concept.titulo)}</h1>
          <p className="secondary-copy">
            Lectura matemática · Fuente LaTeX conservada
          </p>
        </div>
        <div className="study-actions">
          <StudyLink
            to={"/study/concepts/" + encodeURIComponent(concept.key) + "/edit"}
            navigate={navigate}
            className="primary-button"
          >
            Editar concepto
          </StudyLink>
          <StudyLink
            to={"/study/spaces?concept=" + encodeURIComponent(concept.key)}
            navigate={navigate}
          >
            Ver en una esfera
          </StudyLink>
          <button
            aria-expanded={preferences.contextOpen}
            aria-controls="concept-context"
            onClick={() => change({ contextOpen: !preferences.contextOpen })}
          >
            {preferences.contextOpen ? "Ocultar contexto" : "Mostrar contexto"}
          </button>
        </div>
      </header>
      <div
        className="concept-reading-layout"
        data-context={preferences.contextOpen}
        style={
          {
            "--context-width": preferences.contextWidth + "px",
          } as React.CSSProperties
        }
      >
        <article className="concept-paper">
          <ExportActions context={context} conceptKeys={[concept.key]} />
          <DocumentContent
            content={concept.contenido_latex}
            context={context}
          />
        </article>
        {preferences.contextOpen && (
          <aside
            id="concept-context"
            className="concept-context workbench-card"
            aria-label="Procedencia y contexto"
          >
            <header>
              <h2>Procedencia y contexto</h2>
            </header>
            <label>
              Ancho del panel
              <input
                type="range"
                min="240"
                max="440"
                step="20"
                value={preferences.contextWidth}
                onChange={(e) =>
                  change({ contextWidth: Number(e.target.value) })
                }
              />
            </label>
            <section>
              <h3>Fuente</h3>
              {concept.source_id ? (
                <StudyLink
                  to={"/study/sources/" + encodeURIComponent(concept.source_id)}
                  navigate={navigate}
                >
                  Abrir fuente
                </StudyLink>
              ) : (
                <p>Fuente histórica conservada.</p>
              )}
              <dl className="metadata-list">
                {(
                  [
                    ["fuente", "Título"],
                    ["autor", "Autoría"],
                    ["anio", "Año"],
                    ["editorial", "Editorial"],
                    ["capitulo", "Capítulo"],
                    ["seccion", "Sección"],
                    ["paginas", "Páginas"],
                  ] as const
                ).map(
                  ([key, label]) =>
                    reference[key] && (
                      <div key={key}>
                        <dt>{label}</dt>
                        <dd>{bibliographicText(String(reference[key]))}</dd>
                      </div>
                    ),
                )}
              </dl>
              {concept.categorias?.length > 0 && (
                <p>Categorías: {concept.categorias.join(", ")}</p>
              )}
              {concept.comentario && <p>{concept.comentario}</p>}
            </section>
            <section>
              <h3>Origen y pasajes</h3>
              {concept.passages.map((passage, index) => (
                <div key={index}>
                  {passage.quote && <blockquote>{passage.quote}</blockquote>}
                  <StudyLink
                    to={
                      "/study/read/" +
                      encodeURIComponent(passage.document_id) +
                      "?" +
                      new URLSearchParams({
                        page: String(passage.pdf_page ?? 1),
                        ...(passage.annotation_id
                          ? { annotation: passage.annotation_id }
                          : {}),
                      })
                    }
                    navigate={navigate}
                  >
                    Volver al pasaje original
                    {passage.pdf_page
                      ? " · página PDF " + passage.pdf_page
                      : ""}
                  </StudyLink>
                </div>
              ))}
              {concept.passages_state === "unverified" ? (
                <p>
                  No se pudo comprobar el origen de los pasajes. Puedes seguir
                  leyendo.{" "}
                  <button onClick={resource.retry}>
                    Reintentar procedencia
                  </button>
                </p>
              ) : (
                !concept.passages.length && (
                  <p>
                    Este concepto no tiene un pasaje vinculado. Su fuente
                    histórica se conserva.
                  </p>
                )
              )}
            </section>
            <ConceptRelations
              context={context}
              concept={concept}
              navigate={navigate}
              changed={resource.retry}
            />
            <details>
              <summary>Identificadores históricos</summary>
              <dl className="metadata-list">
                <dt>Concepto</dt>
                <dd>{concept.id || concept.key}</dd>
                <dt>Fuente original</dt>
                <dd>{concept.source}</dd>
              </dl>
            </details>
          </aside>
        )}
      </div>
    </section>
  );
}
