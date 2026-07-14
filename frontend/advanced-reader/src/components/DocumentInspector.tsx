import type { DocumentMetadata, PageLabel } from "../types/api";

interface DocumentInspectorProps {
  metadata: DocumentMetadata;
  currentPage: number;
  pageLabel: PageLabel;
}

function formatBytes(bytes: number): string {
  if (!Number.isFinite(bytes) || bytes < 0) return "—";
  if (bytes < 1024 * 1024) return `${Math.round(bytes / 1024)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

export function DocumentInspector({ metadata, currentPage, pageLabel }: DocumentInspectorProps) {
  return (
    <section className="inspector-card" aria-labelledby="document-inspector-heading">
      <div className="eyebrow">Document</div>
      <h2 id="document-inspector-heading">{metadata.title}</h2>
      <dl className="metadata-list">
        <div>
          <dt>Source</dt>
          <dd>{metadata.source.name}</dd>
        </div>
        <div>
          <dt>Reference</dt>
          <dd>{metadata.reference?.title || "—"}</dd>
        </div>
        <div>
          <dt>Archivo</dt>
          <dd>{metadata.version.original_filename}</dd>
        </div>
        <div>
          <dt>Tamaño</dt>
          <dd>{formatBytes(metadata.version.size_bytes)}</dd>
        </div>
        <div>
          <dt>SHA-256</dt>
          <dd><code>{metadata.version.sha256.slice(0, 12)}…</code></dd>
        </div>
        <div>
          <dt>Integridad</dt>
          <dd><span className="status-chip is-ok">Verificada</span></dd>
        </div>
        <div>
          <dt>Reading status</dt>
          <dd>{metadata.reading_state.status}</dd>
        </div>
        <div>
          <dt>PDF page</dt>
          <dd>{currentPage}</dd>
        </div>
        <div>
          <dt>Book page</dt>
          <dd>{pageLabel.book_page_label ?? "—"}</dd>
        </div>
      </dl>
      <p className="page-label" aria-live="polite">{pageLabel.display_label}</p>
      <details>
        <summary>Identificadores técnicos</summary>
        <dl className="technical-ids">
          <dt>Document</dt><dd><code>{metadata.document_id}</code></dd>
          <dt>Version</dt><dd><code>{metadata.version.version_id}</code></dd>
          <dt>Source</dt><dd><code>{metadata.source.source_id}</code></dd>
          {metadata.reference && (
            <><dt>Reference</dt><dd><code>{metadata.reference.reference_id}</code></dd></>
          )}
        </dl>
      </details>
    </section>
  );
}
