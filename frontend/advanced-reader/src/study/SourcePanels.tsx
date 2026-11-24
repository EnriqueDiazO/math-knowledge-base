/** Source-specific document and reference actions; full editors are opened on demand. */
import { useState } from "react";
import {
  bibliographyLabel,
  studyRequest,
  type SourceDetail,
  type StudyContext,
} from "./api";
import type { Navigate } from "./navigation";
import { StudyLink } from "./StudyLink";
import { documentLink } from "../security/document-links";
import { CatalogEditor } from "./CatalogEditor";
import { CatalogStateAction } from "./CatalogStateAction";
import { useOperationScope } from "./useOperationScope";
export function SourceDocuments({
  context,
  source,
  navigate,
  retry,
  pending,
}: {
  context: StudyContext;
  source: SourceDetail;
  navigate: Navigate;
  retry: () => void;
  pending?: (busy: boolean) => void;
}) {
  const [editing, setEditing] = useState("");
  if (editing)
    return (
      <CatalogEditor
        context={context}
        sourceId={source.source_id}
        kind="document"
        identity={editing}
        done={() => {
          setEditing("");
          retry();
        }}
      />
    );
  return (
    <div className="study-library-list">
      {source.documents.map((item) => {
        const document = item as typeof item & {
          revision?: string;
          status?: string;
        };
        return (
          <article key={document.document_id}>
            <h2>{document.title}</h2>
            <p>{document.kind === "pdf" ? "Documento PDF" : "Página web"}</p>
            {document.kind === "web" ? (
              documentLink(document.web_url) ? (
                <a
                  href={documentLink(document.web_url)}
                  target="_blank"
                  rel="noopener noreferrer"
                >
                  Abrir página web
                </a>
              ) : (
                <p>La dirección de esta página necesita revisión.</p>
              )
            ) : (
              <StudyLink
                to={"/study/read/" + encodeURIComponent(document.document_id)}
                navigate={navigate}
              >
                Leer documento
              </StudyLink>
            )}
            <StudyLink
              to={
                "/study/notes?document=" +
                encodeURIComponent(document.document_id)
              }
              navigate={navigate}
            >
              Notas del documento
            </StudyLink>
            <StudyLink
              to={
                "/study/concepts?source=" +
                encodeURIComponent(source.source_id) +
                "&document=" +
                encodeURIComponent(document.document_id)
              }
              navigate={navigate}
            >
              Conceptos derivados del documento
            </StudyLink>
            <button onClick={() => setEditing(document.document_id)}>
              Editar documento
            </button>
            {document.revision && (
              <CatalogStateAction
                key={document.revision}
                context={context}
                path={
                  "/sources/" +
                  encodeURIComponent(source.source_id) +
                  "/documents/" +
                  encodeURIComponent(document.document_id)
                }
                revision={document.revision}
                status={document.status || "active"}
                kind="documento"
                done={retry}
                pending={pending}
              />
            )}
          </article>
        );
      })}
      {!source.documents.length && (
        <p>
          Esta fuente no tiene documentos en este estado. Puedes asociar un PDF
          o una página web.
        </p>
      )}
    </div>
  );
}
export function SourceReferences({
  context,
  source,
  retry,
}: {
  context: StudyContext;
  source: SourceDetail;
  retry: () => void;
}) {
  const [editing, setEditing] = useState("");
  if (editing)
    return (
      <CatalogEditor
        context={context}
        sourceId={source.source_id}
        kind="reference"
        identity={editing}
        done={() => {
          setEditing("");
          retry();
        }}
      />
    );
  return (
    <section aria-label="Bibliografía">
      {source.references.map((reference, index) => (
        <article key={reference.reference_id || index}>
          <h2>{reference.title || source.name}</h2>
          <p>{bibliographyLabel(reference)}</p>
          {reference.source_ids && reference.source_ids.length > 1 && (
            <p>
              Referencia compartida por {reference.source_ids.length} fuentes.
            </p>
          )}
          {documentLink(reference.url) && (
            <a
              href={documentLink(reference.url)}
              target="_blank"
              rel="noopener noreferrer"
            >
              Abrir referencia
            </a>
          )}
          {reference.doi && <p>DOI: {reference.doi}</p>}
          {reference.isbn?.length ? (
            <p>ISBN: {reference.isbn.join(", ")}</p>
          ) : null}
          {reference.reference_id && (
            <>
              <button onClick={() => setEditing(reference.reference_id!)}>
                Editar referencia
              </button>
              {reference.revision && (
                <DetachReference
                  context={context}
                  sourceId={source.source_id}
                  identity={reference.reference_id}
                  revision={reference.revision}
                  done={retry}
                />
              )}
            </>
          )}
        </article>
      ))}
      {!source.references.length && (
        <p>
          Esta fuente todavía no tiene una referencia bibliográfica asociada.
        </p>
      )}
    </section>
  );
}
function DetachReference({
  context,
  sourceId,
  identity,
  revision,
  done,
}: {
  context: StudyContext;
  sourceId: string;
  identity: string;
  revision: string;
  done: () => void;
}) {
  const scope = useOperationScope(context),
    [confirmed, setConfirmed] = useState(false),
    [message, setMessage] = useState(""),
    [busy, setBusy] = useState(false);
  const run = async () => {
    if (!confirmed || busy) return;
    setBusy(true);
    try {
      const result = await studyRequest<{ detached: boolean }>(
        "/sources/" +
          encodeURIComponent(sourceId) +
          "/references/" +
          encodeURIComponent(identity) +
          "/detach",
        context,
        { revision, changes: {} },
      );
      if (scope.active) {
        if (!result.detached)
          throw new Error("No se confirmó la desvinculación.");
        done();
      }
    } catch (error) {
      if (scope.active) setMessage((error as Error).message);
    } finally {
      if (scope.active) setBusy(false);
    }
  };
  return (
    <details>
      <summary>Vinculación de la referencia</summary>
      <p>
        Se retirará sólo de esta fuente. La referencia y sus demás asociaciones
        se conservarán. Si ya está citada aquí, cambia primero esas citas.
      </p>
      <label>
        <input
          type="checkbox"
          checked={confirmed}
          onChange={(event) => setConfirmed(event.target.checked)}
        />
        Confirmar desvinculación
      </label>
      <button disabled={!confirmed || busy} onClick={() => void run()}>
        Desvincular de esta fuente
      </button>
      <p role="status">{message}</p>
    </details>
  );
}
