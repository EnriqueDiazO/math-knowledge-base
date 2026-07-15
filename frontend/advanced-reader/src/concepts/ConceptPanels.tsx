import type {
  ConceptEvidence,
  DocumentConceptGroup,
  UnlinkedVisualAnnotation,
} from "../types/api";

interface ConceptPanelsProps {
  groups: DocumentConceptGroup[];
  unlinked: UnlinkedVisualAnnotation[];
  currentPage: number;
  loading: boolean;
  canLink: boolean;
  canArchive: boolean;
  canReactivate: boolean;
  hasMore: boolean;
  onLoadMore(): void;
  onLink(annotationId: string): void;
  onNavigate(evidence: ConceptEvidence): void;
  onArchive(evidenceLinkId: string): Promise<void>;
  onReactivate(evidenceLinkId: string): Promise<void>;
}

function EvidenceCard({
  evidence,
  canArchive,
  canReactivate,
  onNavigate,
  onArchive,
  onReactivate,
}: {
  evidence: ConceptEvidence;
  canArchive: boolean;
  canReactivate: boolean;
  onNavigate(): void;
  onArchive(): Promise<void>;
  onReactivate(): Promise<void>;
}) {
  return (
    <article className="concept-evidence-card">
      <strong>{evidence.link_type_label}</strong>
      <span>{evidence.status}</span>
      {evidence.annotation !== null && (
        <p>
          {evidence.annotation.kind === "highlight" ? "Highlight" : "Underline"} · PDF page {evidence.annotation.pdf_page}
          {evidence.annotation.book_page_label ? ` · Book page ${evidence.annotation.book_page_label}` : ""}
        </p>
      )}
      {evidence.comment && <p>{evidence.comment}</p>}
      <div className="button-row">
        <button type="button" onClick={onNavigate}>Ir a la marca</button>
        {evidence.status === "active" && canArchive && (
          <button type="button" onClick={() => void onArchive()}>Archivar vínculo</button>
        )}
        {evidence.status === "archived" && canReactivate && (
          <button type="button" onClick={() => void onReactivate()}>Reactivar vínculo</button>
        )}
      </div>
      <details>
        <summary>Ver detalles</summary>
        <p>Source legacy: {evidence.concept.concept_legacy_source}</p>
        <p>{evidence.evidence_link_id}</p>
      </details>
    </article>
  );
}

function ConceptGroup({
  group,
  evidence,
  ...actions
}: {
  group: DocumentConceptGroup;
  evidence: ConceptEvidence[];
  canArchive: boolean;
  canReactivate: boolean;
  onNavigate(evidence: ConceptEvidence): void;
  onArchive(evidenceLinkId: string): Promise<void>;
  onReactivate(evidenceLinkId: string): Promise<void>;
}) {
  const highlights = evidence.filter((item) => item.annotation?.kind === "highlight").length;
  const underlines = evidence.filter((item) => item.annotation?.kind === "underline").length;
  const pages = [...new Set(evidence.flatMap((item) =>
    item.annotation === null ? [] : [item.annotation.pdf_page]))].sort((left, right) => left - right);
  return (
    <article className="concept-group-card">
      <h3>{group.concept.title}</h3>
      <p>{group.concept.concept_type || "Concepto matemático"}</p>
      <p>
        {highlights} highlights · {underlines} underlines · páginas {pages.join(", ")}
      </p>
      <details>
        <summary>Mostrar todas las marcas</summary>
        {evidence.map((item) => (
          <EvidenceCard
            key={item.evidence_link_id}
            evidence={item}
            canArchive={actions.canArchive}
            canReactivate={actions.canReactivate}
            onNavigate={() => actions.onNavigate(item)}
            onArchive={() => actions.onArchive(item.evidence_link_id)}
            onReactivate={() => actions.onReactivate(item.evidence_link_id)}
          />
        ))}
      </details>
    </article>
  );
}

export function ConceptPanels({
  groups,
  unlinked,
  currentPage,
  loading,
  canLink,
  canArchive,
  canReactivate,
  hasMore,
  onLoadMore,
  onLink,
  onNavigate,
  onArchive,
  onReactivate,
}: ConceptPanelsProps) {
  const pageGroups = groups.map((group) => ({
    ...group,
    evidence: group.evidence.filter((item) =>
      item.annotation?.pdf_page === currentPage && item.annotation.status === "active"),
  })).filter((group) => group.evidence.length > 0);

  return (
    <section className="inspector-card concept-panels" aria-labelledby="page-concepts-heading">
      <div className="eyebrow">Evidencia visual</div>
      <h2 id="page-concepts-heading">Conceptos en esta página</h2>
      {pageGroups.map((group) => (
        <ConceptGroup
          key={`page-${group.concept.concept_legacy_source}-${group.concept.concept_legacy_id}`}
          group={group}
          evidence={group.evidence}
          canArchive={canArchive}
          canReactivate={canReactivate}
          onNavigate={onNavigate}
          onArchive={onArchive}
          onReactivate={onReactivate}
        />
      ))}
      {!loading && pageGroups.length === 0 && <p className="muted">No hay conceptos vinculados a marcas en esta página.</p>}

      <h2>Conceptos del documento</h2>
      {groups.map((group) => (
        <ConceptGroup
          key={`document-${group.concept.concept_legacy_source}-${group.concept.concept_legacy_id}`}
          group={group}
          evidence={group.evidence}
          canArchive={canArchive}
          canReactivate={canReactivate}
          onNavigate={onNavigate}
          onArchive={onArchive}
          onReactivate={onReactivate}
        />
      ))}
      {!loading && groups.length === 0 && <p className="muted">Este documento todavía no tiene evidencia conceptual visual.</p>}
      {hasMore && <button type="button" disabled={loading} onClick={onLoadMore}>Cargar más conceptos</button>}

      <h2>Marcas sin concepto</h2>
      {unlinked.map((annotation) => (
        <article className="unlinked-visual-card" key={annotation.annotation_id}>
          <strong>{annotation.kind === "highlight" ? "Highlight" : "Underline"}</strong>
          <p>PDF page {annotation.pdf_page}{annotation.book_page_label ? ` · Book page ${annotation.book_page_label}` : ""}</p>
          <blockquote>{annotation.quote_text}</blockquote>
          {canLink && (
            <button type="button" onClick={() => onLink(annotation.annotation_id)}>Asociar concepto</button>
          )}
        </article>
      ))}
      {!loading && unlinked.length === 0 && <p className="muted">No hay marcas activas pendientes en esta página.</p>}
      {loading && <p className="muted" role="status">Cargando evidencia visual…</p>}
      <p className="future-note">Este panel muestra evidencia visual; la evidencia S4 completa permanece en Reading Space.</p>
    </section>
  );
}
