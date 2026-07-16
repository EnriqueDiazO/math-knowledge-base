import { useEffect, useState } from "react";

import { ReaderApiError } from "../api/client";
import type { AdvancedReaderApi } from "../api/client";
import type {
  ConceptEvidence,
  ConceptSummary,
  DocumentMetadata,
  EvidenceLinkType,
  VisualAnnotation,
} from "../types/api";
import { EVIDENCE_LINK_OPTIONS, evidenceLinkLabel } from "./labels";

interface ConceptLinkWizardProps {
  api: AdvancedReaderApi;
  metadata: DocumentMetadata;
  annotation: VisualAnnotation;
  canWrite: boolean;
  onSaved(evidence: ConceptEvidence): void;
  onCancel(): void;
}

function newEvidenceLinkId(): string | null {
  return typeof window.crypto?.randomUUID === "function"
    ? `ev_${window.crypto.randomUUID()}`
    : null;
}

function conceptTopics(concept: ConceptSummary): string {
  return [...concept.categories, ...concept.tags].slice(0, 5).join(" · ");
}

export function ConceptLinkWizard({
  api,
  metadata,
  annotation,
  canWrite,
  onSaved,
  onCancel,
}: ConceptLinkWizardProps) {
  const [query, setQuery] = useState("");
  const [results, setResults] = useState<ConceptSummary[]>([]);
  const [searchPage, setSearchPage] = useState(1);
  const [hasMore, setHasMore] = useState(false);
  const [searching, setSearching] = useState(false);
  const [searchError, setSearchError] = useState<string | null>(null);
  const [searched, setSearched] = useState(false);
  const [selected, setSelected] = useState<ConceptSummary | null>(null);
  const [linkType, setLinkType] = useState<EvidenceLinkType>("related_context");
  const [comment, setComment] = useState("");
  const [pendingEvidenceLinkId, setPendingEvidenceLinkId] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [saveError, setSaveError] = useState<string | null>(null);
  const [moreOptions, setMoreOptions] = useState(false);

  useEffect(() => {
    setQuery("");
    setResults([]);
    setSearchPage(1);
    setHasMore(false);
    setSearchError(null);
    setSearched(false);
    setSelected(null);
    setLinkType("related_context");
    setComment("");
    setPendingEvidenceLinkId(null);
    setSaving(false);
    setSaveError(null);
    setMoreOptions(false);
  }, [annotation.annotation_id, metadata.document_id, metadata.version.version_id]);

  const search = async (page: number, append: boolean) => {
    const value = query.trim();
    if (!value || Array.from(value).length > 160 || searching) return;
    setSearching(true);
    setSearchError(null);
    setSearched(true);
    try {
      const response = await api.searchConcepts(value, { page, limit: 20 });
      setResults((current) => append ? [...current, ...response.items] : response.items);
      setSearchPage(response.page);
      setHasMore(response.has_more);
    } catch {
      setSearchError("No se pudo buscar conceptos. La consulta no se guardó.");
    } finally {
      setSearching(false);
    }
  };

  const save = async () => {
    if (!canWrite || selected === null || saving) return;
    let evidenceLinkId = pendingEvidenceLinkId;
    if (evidenceLinkId === null) {
      evidenceLinkId = newEvidenceLinkId();
      if (evidenceLinkId === null) {
        setSaveError("Este navegador no ofrece un generador seguro de identidad.");
        return;
      }
      setPendingEvidenceLinkId(evidenceLinkId);
    }
    setSaving(true);
    setSaveError(null);
    try {
      const response = await api.createAnnotationConceptEvidence(annotation.annotation_id, {
        evidence_link_id: evidenceLinkId,
        concept_legacy_id: selected.concept_legacy_id,
        concept_legacy_source: selected.concept_legacy_source,
        link_type: linkType,
        comment: comment.trim() || null,
      });
      onSaved(response.item);
    } catch (reason) {
      const message = reason instanceof ReaderApiError && reason.code === "concept_linking_not_ready"
        ? "Guardar no está disponible. Revisa la configuración."
        : "No se pudo guardar el vínculo. Puedes reintentar sin duplicarlo.";
      setSaveError(message);
    } finally {
      setSaving(false);
    }
  };

  return (
    <section className="inspector-card concept-wizard" aria-labelledby="concept-wizard-heading">
      <div className="eyebrow">Asociando concepto</div>
      <h2 id="concept-wizard-heading">Asociar concepto</h2>
      <blockquote className="selection-text">{annotation.quote_text}</blockquote>
      <p className="visual-page-label">
        PDF page {annotation.pdf_page}{annotation.page_label ? ` · Book page ${annotation.page_label}` : ""}
      </p>

      <form onSubmit={(event) => { event.preventDefault(); void search(1, false); }}>
        <label>
          Buscar concepto
          <input
            aria-label="Buscar concepto"
            value={query}
            maxLength={160}
            disabled={searching}
            onChange={(event) => setQuery(event.target.value)}
          />
        </label>
        <button type="submit" disabled={searching || !query.trim()}>
          {searching ? "Buscando…" : "Buscar"}
        </button>
      </form>
      {searchError !== null && <p role="alert" className="save-feedback error">{searchError}</p>}
      {searched && !searching && results.length === 0 && searchError === null && (
        <p className="muted">No se encontraron conceptos.</p>
      )}
      <div className="concept-card-list" aria-label="Resultados de conceptos">
        {results.map((concept) => {
          const isSelected = selected?.concept_legacy_id === concept.concept_legacy_id &&
            selected.concept_legacy_source === concept.concept_legacy_source;
          return (
            <article
              className={isSelected ? "concept-card selected" : "concept-card"}
              key={`${concept.concept_legacy_source}\u0000${concept.concept_legacy_id}`}
            >
              <h3>{concept.title || "Concepto sin título"}</h3>
              <p>{concept.concept_type || "Concepto matemático"}</p>
              {conceptTopics(concept) && <p>{conceptTopics(concept)}</p>}
              <button type="button" onClick={() => setSelected(concept)}>
                {isSelected ? "Seleccionado ✓" : "Seleccionar"}
              </button>
            </article>
          );
        })}
      </div>
      {hasMore && (
        <button type="button" disabled={searching} onClick={() => void search(searchPage + 1, true)}>
          Más resultados
        </button>
      )}

      {selected !== null && (
        <article className="concept-card selected selected-concept" aria-label="Concepto seleccionado">
          <div className="eyebrow">Concepto seleccionado</div>
          <h3>{selected.title || "Concepto sin título"}</h3>
          <p>
            Relación: {evidenceLinkLabel(linkType)} ·{" "}
            <button type="button" className="text-button" onClick={() => setMoreOptions(true)}>
              Cambiar
            </button>
          </p>
        </article>
      )}

      {moreOptions && (
        <div className="more-options" aria-label="Más opciones">
          <label>
            Relación
            <select
              aria-label="Tipo de evidencia"
              value={linkType}
              onChange={(event) => setLinkType(event.target.value as EvidenceLinkType)}
            >
              {EVIDENCE_LINK_OPTIONS.map((option) => (
                <option key={option.value} value={option.value}>{option.label}</option>
              ))}
            </select>
          </label>
          <label>
            Comentario
            <textarea
              aria-label="Comentario del vínculo"
              rows={3}
              maxLength={100_000}
              value={comment}
              onChange={(event) => setComment(event.target.value)}
            />
          </label>
        </div>
      )}
      {!canWrite && <p className="warning-banner">Guardar no está disponible. Revisa la configuración.</p>}
      {saveError !== null && <p className="save-feedback error" role="alert">{saveError}</p>}
      <div className="button-row">
        <button
          type="button"
          className="primary-button"
          disabled={selected === null || saving || !canWrite}
          onClick={() => void save()}
        >
          {saving ? "Guardando…" : saveError ? "Reintentar" : "Guardar"}
        </button>
        <button type="button" disabled={saving} onClick={onCancel}>Cancelar</button>
      </div>
    </section>
  );
}
