import { useEffect, useMemo, useState } from "react";

import {
  VISUAL_ANNOTATION_COLORS,
  parseVisualAnnotationTags,
  visualAnnotationColor,
  visualQuotePreview,
} from "../annotations/ui";
import type {
  ConceptEvidence,
  UpdateVisualAnnotation,
  VisualAnnotation,
  VisualAnnotationColor,
  VisualAnnotationKind,
} from "../types/api";

export interface VisualAnnotationFilters {
  scope: "page" | "document";
  status: "active" | "archived" | "all";
  kind: "all" | VisualAnnotationKind;
}

interface VisualAnnotationsPanelProps {
  annotations: VisualAnnotation[];
  currentPage: number;
  filters: VisualAnnotationFilters;
  loading: boolean;
  hasMore: boolean;
  canMutate: boolean;
  canLinkConcepts: boolean;
  canArchiveConceptLinks: boolean;
  canReactivateConceptLinks: boolean;
  conceptEvidenceByAnnotation: Record<string, ConceptEvidence[]>;
  onFilters(filters: VisualAnnotationFilters): void;
  onLoadMore(): void;
  onNavigate(annotation: VisualAnnotation): void;
  onUpdate(annotationId: string, patch: UpdateVisualAnnotation): Promise<void>;
  onArchive(annotationId: string): Promise<void>;
  onReactivate(annotationId: string): Promise<void>;
  onLinkConcept(annotation: VisualAnnotation): void;
  onArchiveConceptLink(evidenceLinkId: string): Promise<void>;
  onReactivateConceptLink(evidenceLinkId: string): Promise<void>;
}

interface EditDraft {
  kind: VisualAnnotationKind;
  color: VisualAnnotationColor;
  body: string;
  tagsText: string;
}

function editDraft(annotation: VisualAnnotation): EditDraft {
  return {
    kind: annotation.kind,
    color: visualAnnotationColor(annotation.color_label),
    body: annotation.body,
    tagsText: annotation.tags.join(", "),
  };
}

export function VisualAnnotationsPanel({
  annotations,
  currentPage,
  filters,
  loading,
  hasMore,
  canMutate,
  canLinkConcepts,
  canArchiveConceptLinks,
  canReactivateConceptLinks,
  conceptEvidenceByAnnotation,
  onFilters,
  onLoadMore,
  onNavigate,
  onUpdate,
  onArchive,
  onReactivate,
  onLinkConcept,
  onArchiveConceptLink,
  onReactivateConceptLink,
}: VisualAnnotationsPanelProps) {
  const [editing, setEditing] = useState<string | null>(null);
  const [draft, setDraft] = useState<EditDraft | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (editing !== null && !annotations.some((item) => item.annotation_id === editing)) {
      setEditing(null);
      setDraft(null);
    }
  }, [annotations, editing]);

  const visible = useMemo(() => annotations.filter((annotation) => (
    (filters.scope === "document" || annotation.pdf_page === currentPage) &&
    (filters.status === "all" || annotation.status === filters.status) &&
    (filters.kind === "all" || annotation.kind === filters.kind)
  )), [annotations, currentPage, filters]);

  const run = async (annotationId: string, operation: () => Promise<void>) => {
    setBusy(annotationId);
    setError(null);
    try {
      await operation();
    } catch {
      setError("No se pudo actualizar la anotación visual.");
    } finally {
      setBusy(null);
    }
  };

  return (
    <section className="inspector-card visual-annotations" aria-labelledby="visual-list-heading">
      <div className="eyebrow">Notes &amp; Evidence</div>
      <h2 id="visual-list-heading">Anotaciones visuales</h2>
      <div className="visual-filters" aria-label="Filtros de anotaciones visuales">
        <label>
          Alcance
          <select
            aria-label="Alcance de anotaciones"
            value={filters.scope}
            onChange={(event) => onFilters({
              ...filters,
              scope: event.target.value as VisualAnnotationFilters["scope"],
            })}
          >
            <option value="page">Página actual</option>
            <option value="document">Todo el documento</option>
          </select>
        </label>
        <label>
          Estado
          <select
            aria-label="Estado de anotaciones"
            value={filters.status}
            onChange={(event) => onFilters({
              ...filters,
              status: event.target.value as VisualAnnotationFilters["status"],
            })}
          >
            <option value="active">Active</option>
            <option value="archived">Archived</option>
            <option value="all">Todos</option>
          </select>
        </label>
        <label>
          Tipo
          <select
            aria-label="Tipo de anotaciones"
            value={filters.kind}
            onChange={(event) => onFilters({
              ...filters,
              kind: event.target.value as VisualAnnotationFilters["kind"],
            })}
          >
            <option value="all">Todos</option>
            <option value="highlight">Highlight</option>
            <option value="underline">Underline</option>
          </select>
        </label>
      </div>
      {!canMutate && (
        <p className="warning-banner" role="status">
          Inicializa Notes &amp; Evidence en Maintenance para guardar marcas visuales.
        </p>
      )}
      {error !== null && <p className="save-feedback error" role="alert">{error}</p>}
      <div className="visual-card-list">
        {visible.map((annotation) => {
          const isEditing = editing === annotation.annotation_id && draft !== null;
          const isBusy = busy === annotation.annotation_id;
          const conceptEvidence = conceptEvidenceByAnnotation[annotation.annotation_id] ?? [];
          return (
            <article
              key={annotation.annotation_id}
              className={`visual-card color-${visualAnnotationColor(annotation.color_label)}`}
              data-annotation-id={annotation.annotation_id}
            >
              <header>
                <strong>{annotation.kind === "highlight" ? "Highlight" : "Underline"}</strong>
                <span>
                  {visualAnnotationColor(annotation.color_label)} · {annotation.status}
                </span>
              </header>
              {annotation.visual_status === "version_mismatch" && (
                <p className="warning-banner">Anotación visual asociada a otra versión del PDF.</p>
              )}
              {annotation.visual_status === "invalid_geometry" && (
                <p className="warning-banner">La geometría persistida no es válida.</p>
              )}
              <p className="visual-page-label">
                PDF page {annotation.pdf_page}
                {annotation.page_label ? ` · Book page ${annotation.page_label}` : ""}
              </p>
              <blockquote>{visualQuotePreview(annotation.quote_text)}</blockquote>
              {!isEditing && annotation.body && <p>{annotation.body}</p>}
              {!isEditing && annotation.tags.length > 0 && (
                <ul className="tag-list" aria-label="Tags">
                  {annotation.tags.map((tag) => <li key={tag}>{tag}</li>)}
                </ul>
              )}
              {isEditing && (
                <div className="visual-edit-form">
                  <label>
                    Tipo
                    <select
                      aria-label={`Editar tipo ${annotation.annotation_id}`}
                      value={draft.kind}
                      disabled={isBusy}
                      onChange={(event) => setDraft({
                        ...draft,
                        kind: event.target.value as VisualAnnotationKind,
                      })}
                    >
                      <option value="highlight">Highlight</option>
                      <option value="underline">Underline</option>
                    </select>
                  </label>
                  <label>
                    Color
                    <select
                      aria-label={`Editar color ${annotation.annotation_id}`}
                      value={draft.color}
                      disabled={isBusy}
                      onChange={(event) => setDraft({
                        ...draft,
                        color: event.target.value as VisualAnnotationColor,
                      })}
                    >
                      {VISUAL_ANNOTATION_COLORS.map((color) => (
                        <option key={color} value={color}>{color}</option>
                      ))}
                    </select>
                  </label>
                  <label>
                    Comentario
                    <textarea
                      aria-label={`Editar comentario ${annotation.annotation_id}`}
                      rows={3}
                      maxLength={50_000}
                      value={draft.body}
                      disabled={isBusy}
                      onChange={(event) => setDraft({ ...draft, body: event.target.value })}
                    />
                  </label>
                  <label>
                    Tags
                    <input
                      aria-label={`Editar tags ${annotation.annotation_id}`}
                      maxLength={5_000}
                      value={draft.tagsText}
                      disabled={isBusy}
                      onChange={(event) => setDraft({ ...draft, tagsText: event.target.value })}
                    />
                  </label>
                </div>
              )}
              <div className="button-row">
                <button type="button" disabled={isBusy} onClick={() => onNavigate(annotation)}>
                  Ir a página
                </button>
                {canMutate && !isEditing && (
                  <button type="button" disabled={isBusy} onClick={() => {
                    setEditing(annotation.annotation_id);
                    setDraft(editDraft(annotation));
                  }}>
                    Editar
                  </button>
                )}
                {canMutate && isEditing && (
                  <>
                    <button
                      type="button"
                      className="primary-button"
                      disabled={isBusy}
                      onClick={() => void run(annotation.annotation_id, async () => {
                        await onUpdate(annotation.annotation_id, {
                          kind: draft.kind,
                          color_label: draft.color,
                          body: draft.body,
                          tags: parseVisualAnnotationTags(draft.tagsText),
                        });
                        setEditing(null);
                        setDraft(null);
                      })}
                    >
                      Guardar cambios
                    </button>
                    <button type="button" disabled={isBusy} onClick={() => {
                      setEditing(null);
                      setDraft(null);
                    }}>Cancelar</button>
                  </>
                )}
                {canMutate && annotation.status === "active" && !isEditing && (
                  <button
                    type="button"
                    disabled={isBusy}
                    onClick={() => void run(
                      annotation.annotation_id,
                      () => onArchive(annotation.annotation_id),
                    )}
                  >
                    Archivar
                  </button>
                )}
                {canMutate && annotation.status === "archived" && !isEditing && (
                  <button
                    type="button"
                    disabled={isBusy}
                    onClick={() => void run(
                      annotation.annotation_id,
                      () => onReactivate(annotation.annotation_id),
                    )}
                  >
                    Reactivar
                  </button>
                )}
                {canLinkConcepts && annotation.status === "active" &&
                  annotation.visual_status === "exact" && !isEditing && (
                  <button type="button" disabled={isBusy} onClick={() => onLinkConcept(annotation)}>
                    Asociar concepto
                  </button>
                )}
              </div>
              <section className="annotation-concepts" aria-label="Conceptos asociados">
                <h3>Conceptos asociados</h3>
                {conceptEvidence.map((evidence) => (
                  <article key={evidence.evidence_link_id} className="annotation-concept-card">
                    <strong>{evidence.concept.title}</strong>
                    <p>{evidence.link_type_label} · {evidence.status}</p>
                    {evidence.comment && <p>{evidence.comment}</p>}
                    <p>Source legacy: {evidence.concept.concept_legacy_source}</p>
                    <div className="button-row">
                      <button type="button" onClick={() => onNavigate(annotation)}>Ir a la marca</button>
                      {evidence.status === "active" && canArchiveConceptLinks && (
                        <button
                          type="button"
                          onClick={() => void onArchiveConceptLink(evidence.evidence_link_id)}
                        >
                          Archivar vínculo
                        </button>
                      )}
                      {evidence.status === "archived" && annotation.status === "active" &&
                        canReactivateConceptLinks && (
                        <button
                          type="button"
                          onClick={() => void onReactivateConceptLink(evidence.evidence_link_id)}
                        >
                          Reactivar vínculo
                        </button>
                      )}
                    </div>
                    {evidence.status === "archived" && annotation.status === "archived" && (
                      <p className="muted">Reactiva primero la marca visual para reactivar el vínculo.</p>
                    )}
                    <details><summary>Ver detalles</summary><p>{evidence.evidence_link_id}</p></details>
                  </article>
                ))}
                {conceptEvidence.length === 0 && <p className="muted">Sin conceptos asociados.</p>}
              </section>
              <details>
                <summary>Mostrar detalles técnicos</summary>
                <dl className="technical-ids">
                  <dt>Version</dt><dd>{annotation.visual_anchor.version_id}</dd>
                  <dt>SHA</dt><dd>{annotation.visual_anchor.document_sha256.slice(0, 12)}…</dd>
                  <dt>Space</dt><dd>{annotation.visual_anchor.coordinate_space}</dd>
                  <dt>Rotation</dt><dd>{annotation.visual_anchor.capture_rotation}°</dd>
                  <dt>Rects</dt><dd>{annotation.visual_anchor.rects.length}</dd>
                </dl>
              </details>
            </article>
          );
        })}
      </div>
      {loading && <p className="muted" role="status">Cargando anotaciones…</p>}
      {!loading && visible.length === 0 && <p className="muted">No hay marcas para este filtro.</p>}
      {filters.scope === "document" && hasMore && (
        <button type="button" disabled={loading} onClick={onLoadMore}>Cargar más</button>
      )}
    </section>
  );
}
