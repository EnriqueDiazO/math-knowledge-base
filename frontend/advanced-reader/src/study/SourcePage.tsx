/** Contextual source workspace: documents, references, notes and derived concepts. */
import { useState } from "react";
import { useStudyResource, type Navigate } from "./navigation";
import type { SourceDetail, StudyContext } from "./api";
import { StudyLink } from "./StudyLink";
import { ReferenceForm } from "./ReferenceForm";
import { DocumentForm } from "./DocumentForm";
import { CatalogEditor } from "./CatalogEditor";
import { CatalogStateAction } from "./CatalogStateAction";
import { BibtexImport } from "./BibtexImport";
import { SourceDocuments, SourceReferences } from "./SourcePanels";
export function SourcePage({
  context,
  sourceId,
  navigate,
}: {
  context: StudyContext;
  sourceId: string;
  navigate: Navigate;
}) {
  const [section, setSection] = useState("documents"),
    [message, setMessage] = useState(""),
    [documentPage, setDocumentPage] = useState(1),
    [referencePage, setReferencePage] = useState(1),
    [documentStatus, setDocumentStatus] = useState("active");
  const base = "/sources/" + encodeURIComponent(sourceId);
  const resource = useStudyResource<SourceDetail>(
    context,
    base +
      "?" +
      new URLSearchParams({
        document_page: String(documentPage),
        reference_page: String(referencePage),
        document_status: documentStatus,
      }),
  );
  if (resource.error)
    return (
      <p role="alert">
        {resource.error}
        <button onClick={resource.retry}>Reintentar fuente</button>
      </p>
    );
  const source = resource.data;
  if (!source) return <p role="status">Abriendo la fuente…</p>;
  const saved = (tab: string) => {
    resource.retry();
    setSection(tab);
    setMessage("Datos guardados y confirmados en esta biblioteca.");
  };
  return (
    <section>
      <StudyLink to="/study/library" navigate={navigate}>
        Volver a Biblioteca
      </StudyLink>
      <header>
        <p className="eyebrow">Fuente de estudio</p>
        <h1>{source.name}</h1>
        <p>{source.description}</p>
        {source.status === "archived" && (
          <p>
            Fuente archivada. Sus datos se conservan; reactívala para volver a
            trabajar con ella.
          </p>
        )}
      </header>
      <p role="status">{message}</p>
      <div className="study-actions">
        <button onClick={() => setSection("edit-source")}>Editar fuente</button>
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
          Referencias
        </button>
        <StudyLink
          to={"/study/notes?source=" + encodeURIComponent(sourceId)}
          navigate={navigate}
        >
          Notas de esta fuente
        </StudyLink>
        <StudyLink
          to={"/study/concepts?source=" + encodeURIComponent(sourceId)}
          navigate={navigate}
        >
          Conceptos de esta fuente
        </StudyLink>
      </div>
      {source.status !== "archived" && (
        <div className="study-actions">
          <button onClick={() => setSection("add-document")}>
            + Asociar documento
          </button>
          <button onClick={() => setSection("add-reference")}>
            + Añadir referencia
          </button>
          <button onClick={() => setSection("bibtex")}>Importar BibTeX</button>
          <StudyLink
            to={"/study/write?source=" + encodeURIComponent(sourceId)}
            navigate={navigate}
          >
            Escribir nota sobre esta fuente
          </StudyLink>
          <StudyLink
            to={
              "/study/concepts/new?" + new URLSearchParams({ source: sourceId })
            }
            navigate={navigate}
          >
            + Crear concepto desde esta fuente
          </StudyLink>
        </div>
      )}
      {section === "edit-source" ? (
        <CatalogEditor
          context={context}
          sourceId={sourceId}
          identity={sourceId}
          kind="source"
          done={() => saved("documents")}
        />
      ) : section === "add-reference" ? (
        <ReferenceForm
          context={context}
          sourceId={sourceId}
          done={() => saved("references")}
        />
      ) : section === "add-document" ? (
        <DocumentForm
          context={context}
          source={source}
          done={() => saved("documents")}
        />
      ) : section === "bibtex" ? (
        <BibtexImport
          context={context}
          sourceId={sourceId}
          done={() => saved("references")}
        />
      ) : section === "references" ? (
        <SourceReferences
          context={context}
          source={source}
          retry={resource.retry}
        />
      ) : (
        <>
          <label>
            Estado de los documentos
            <select
              value={documentStatus}
              onChange={(event) => {
                setDocumentStatus(event.target.value);
                setDocumentPage(1);
              }}
            >
              <option value="active">Activos</option>
              <option value="archived">Archivados</option>
            </select>
          </label>
          <SourceDocuments
            context={context}
            source={source}
            navigate={navigate}
            retry={resource.retry}
          />
        </>
      )}
      {section === "documents" && (
        <nav aria-label="Páginas de documentos">
          {documentPage > 1 && (
            <button onClick={() => setDocumentPage(documentPage - 1)}>
              Documentos anteriores
            </button>
          )}
          {documentPage * 100 < (source.document_count || 0) && (
            <button onClick={() => setDocumentPage(documentPage + 1)}>
              Más documentos
            </button>
          )}
        </nav>
      )}
      {section === "references" && (
        <nav aria-label="Páginas de referencias">
          {referencePage > 1 && (
            <button onClick={() => setReferencePage(referencePage - 1)}>
              Referencias anteriores
            </button>
          )}
          {referencePage * 100 < (source.reference_count || 0) && (
            <button onClick={() => setReferencePage(referencePage + 1)}>
              Más referencias
            </button>
          )}
        </nav>
      )}
      {source.revision && (
        <CatalogStateAction
          key={source.revision}
          context={context}
          path={base}
          kind="fuente"
          status={source.status || "active"}
          revision={source.revision}
          done={() => {
            resource.retry();
            setMessage(
              "Estado de la fuente confirmado. Sus recursos se conservan.",
            );
          }}
        />
      )}
    </section>
  );
}
