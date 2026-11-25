/** Contextual bibliographic detail reuses existing source/document/reference operations. */
import type { SourceDetail, StudyContext } from "./api";
import { bibliographyLabel } from "./api";
import { useStudyResource, type Navigate } from "./navigation";
import { StudyLink } from "./StudyLink";
import { bibliographicText } from "./bibliographic-text";
export function SourceSummaryPanel({
  context,
  identity,
  navigate,
  close,
}: {
  context: StudyContext;
  identity: string;
  navigate: Navigate;
  close: () => void;
}) {
  const resource = useStudyResource<SourceDetail>(
      context,
      "/sources/" + encodeURIComponent(identity),
    ),
    source = resource.data,
    base = "/study/sources/" + encodeURIComponent(identity);
  return (
    <aside
      className="library-detail workbench-card"
      aria-label="Detalle de la fuente seleccionada"
    >
      <header>
        <p className="eyebrow">Fuente seleccionada</p>
        <button onClick={close} aria-label="Cerrar detalle de fuente">
          Cerrar
        </button>
      </header>
      {resource.error && (
        <p role="alert">
          {resource.error}{" "}
          <button onClick={resource.retry}>Reintentar detalle</button>
        </p>
      )}
      {source ? (
        <>
          <h2>{bibliographicText(source.name)}</h2>
          {source.description && <p>{bibliographicText(source.description)}</p>}
          <div className="context-actions">
            <StudyLink to={base} navigate={navigate} className="primary-button">
              Abrir fuente
            </StudyLink>
            <StudyLink to={base + "?section=documents"} navigate={navigate}>
              Documentos
            </StudyLink>
            <StudyLink to={base + "?section=edit-source"} navigate={navigate}>
              Editar fuente
            </StudyLink>
            <StudyLink to={base + "?section=references"} navigate={navigate}>
              Referencias
            </StudyLink>
          </div>
          <dl className="metadata-list">
            <dt>Documentos</dt>
            <dd>{source.document_count ?? source.documents.length}</dd>
            <dt>Referencias</dt>
            <dd>{source.reference_count ?? source.references.length}</dd>
            <dt>Estado</dt>
            <dd>{source.status === "archived" ? "Archivada" : "Activa"}</dd>
          </dl>
          <section>
            <h3>Bibliografía</h3>
            {source.references.length ? (
              source.references.slice(0, 4).map((r, index) => (
                <div
                  className="bibliography-entry"
                  key={r.reference_id || index}
                >
                  <strong>{bibliographicText(r.title)}</strong>
                  <p>{bibliographicText(bibliographyLabel(r))}</p>
                  {r.doi && <small>DOI: {r.doi}</small>}
                </div>
              ))
            ) : (
              <p>Todavía no hay referencias asociadas.</p>
            )}
          </section>
          <div className="context-actions">
            <StudyLink
              to={"/study/notes?source=" + encodeURIComponent(identity)}
              navigate={navigate}
            >
              Notas de esta fuente
            </StudyLink>
            <StudyLink
              to={"/study/concepts?source=" + encodeURIComponent(identity)}
              navigate={navigate}
            >
              Conceptos asociados
            </StudyLink>
          </div>
          <details>
            <summary>Identificadores históricos</summary>
            <dl className="metadata-list">
              <dt>Source ID</dt>
              <dd>{source.source_id}</dd>
              <dt>Nombre original</dt>
              <dd>{source.name}</dd>
            </dl>
          </details>
        </>
      ) : (
        !resource.error && (
          <p role="status">Cargando información de la fuente…</p>
        )
      )}
    </aside>
  );
}
