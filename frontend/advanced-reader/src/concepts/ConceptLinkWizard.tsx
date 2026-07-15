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

type WizardStep = "concept" | "relationship" | "confirm";

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
  const [step, setStep] = useState<WizardStep>("concept");
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

  useEffect(() => {
    setStep("concept");
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

  const beginConfirmation = () => {
    if (selected === null) return;
    if (pendingEvidenceLinkId === null) {
      const identity = newEvidenceLinkId();
      if (identity === null) {
        setSaveError("Este navegador no ofrece un generador seguro de identidad.");
        return;
      }
      setPendingEvidenceLinkId(identity);
    }
    setSaveError(null);
    setStep("confirm");
  };

  const save = async () => {
    if (!canWrite || selected === null || pendingEvidenceLinkId === null || saving) return;
    setSaving(true);
    setSaveError(null);
    try {
      const response = await api.createAnnotationConceptEvidence(annotation.annotation_id, {
        evidence_link_id: pendingEvidenceLinkId,
        concept_legacy_id: selected.concept_legacy_id,
        concept_legacy_source: selected.concept_legacy_source,
        link_type: linkType,
        comment: comment.trim() || null,
      });
      onSaved(response.item);
    } catch (reason) {
      const message = reason instanceof ReaderApiError && reason.code === "concept_linking_not_ready"
        ? "Inicializa Notes & Evidence en Maintenance para asociar conceptos."
        : "No se pudo guardar el vínculo. Puedes reintentar sin duplicarlo.";
      setSaveError(message);
    } finally {
      setSaving(false);
    }
  };

  return (
    <section className="inspector-card concept-wizard" aria-labelledby="concept-wizard-heading">
      <div className="eyebrow">Asociación guiada</div>
      <h2 id="concept-wizard-heading">Asociar concepto</h2>
      <ol className="wizard-steps" aria-label="Pasos de asociación">
        <li aria-current={step === "concept" ? "step" : undefined}>1. Concepto</li>
        <li aria-current={step === "relationship" ? "step" : undefined}>2. Relación</li>
        <li aria-current={step === "confirm" ? "step" : undefined}>3. Confirmar</li>
      </ol>

      {step === "concept" && (
        <div className="concept-step">
          <form onSubmit={(event) => { event.preventDefault(); void search(1, false); }}>
            <label>
              Buscar concepto legacy
              <input
                aria-label="Buscar concepto legacy"
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
          <div className="concept-card-list">
            {results.map((concept) => (
              <article
                className={selected === concept ? "concept-card selected" : "concept-card"}
                key={`${concept.concept_legacy_source}\u0000${concept.concept_legacy_id}`}
              >
                <h3>{concept.title || "Concepto sin título"}</h3>
                <p>{concept.concept_type || "Concepto matemático"}</p>
                {conceptTopics(concept) && <p>{conceptTopics(concept)}</p>}
                <p>Source legacy: {concept.concept_legacy_source}</p>
                {concept.evidence_count !== null && <p>{concept.evidence_count} evidencias</p>}
                <button type="button" onClick={() => setSelected(concept)}>Seleccionar</button>
              </article>
            ))}
          </div>
          {hasMore && (
            <button type="button" disabled={searching} onClick={() => void search(searchPage + 1, true)}>
              Más resultados
            </button>
          )}
          <div className="button-row">
            <button
              type="button"
              className="primary-button"
              disabled={selected === null}
              onClick={() => setStep("relationship")}
            >
              Continuar
            </button>
            <button type="button" onClick={onCancel}>Cancelar</button>
          </div>
        </div>
      )}

      {step === "relationship" && selected !== null && (
        <div className="concept-step">
          <article className="concept-card selected">
            <h3>{selected.title}</h3>
            <p>{selected.concept_type || "Concepto matemático"}</p>
            <p>Source legacy: {selected.concept_legacy_source}</p>
            <button type="button" onClick={() => { setSelected(null); setStep("concept"); }}>
              Cambiar concepto
            </button>
          </article>
          <label>
            Tipo de evidencia
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
          <p className="muted">
            {EVIDENCE_LINK_OPTIONS.find((option) => option.value === linkType)?.help}
          </p>
          <label>
            Comentario opcional del vínculo
            <textarea
              aria-label="Comentario del vínculo"
              rows={3}
              maxLength={100_000}
              value={comment}
              onChange={(event) => setComment(event.target.value)}
            />
          </label>
          <article className="annotation-preview">
            <strong>{annotation.kind === "highlight" ? "Highlight" : "Underline"}</strong>
            <blockquote>{annotation.quote_text}</blockquote>
            <p>PDF page {annotation.pdf_page} · Book page {annotation.page_label ?? "—"}</p>
            {annotation.body && <p>{annotation.body}</p>}
          </article>
          <div className="button-row">
            <button type="button" onClick={() => setStep("concept")}>Atrás</button>
            <button type="button" className="primary-button" onClick={beginConfirmation}>
              Revisar
            </button>
            <button type="button" onClick={onCancel}>Cancelar</button>
          </div>
        </div>
      )}

      {step === "confirm" && selected !== null && (
        <div className="concept-step">
          <dl className="metadata-list compact">
            <div><dt>Concepto</dt><dd>{selected.title}</dd></div>
            <div><dt>Source legacy</dt><dd>{selected.concept_legacy_source}</dd></div>
            <div><dt>Relación</dt><dd>{evidenceLinkLabel(linkType)}</dd></div>
            <div><dt>Marca</dt><dd>{annotation.kind === "highlight" ? "Highlight" : "Underline"}</dd></div>
            <div><dt>Página</dt><dd>PDF {annotation.pdf_page} · Book {annotation.page_label ?? "—"}</dd></div>
            <div><dt>Documento</dt><dd>{metadata.title}</dd></div>
            <div><dt>Source</dt><dd>{metadata.source.name}</dd></div>
            <div><dt>Reference</dt><dd>{metadata.reference?.title ?? "—"}</dd></div>
          </dl>
          {comment.trim() && <p>{comment}</p>}
          <details>
            <summary>Detalles técnicos</summary>
            <p>{annotation.annotation_id}</p>
            <p>{pendingEvidenceLinkId}</p>
            <p>{selected.concept_legacy_id} · {selected.concept_legacy_source}</p>
          </details>
          {!canWrite && (
            <p className="warning-banner" role="status">
              Inicializa Notes &amp; Evidence en Maintenance para asociar conceptos.
            </p>
          )}
          {saveError !== null && <p className="save-feedback error" role="alert">{saveError}</p>}
          <div className="button-row">
            <button type="button" disabled={saving} onClick={() => setStep("relationship")}>Atrás</button>
            <button
              type="button"
              className="primary-button"
              disabled={saving || !canWrite}
              onClick={() => void save()}
            >
              {saving ? "Guardando…" : saveError ? "Reintentar" : "Guardar"}
            </button>
            <button type="button" disabled={saving} onClick={onCancel}>Cancelar</button>
          </div>
        </div>
      )}
    </section>
  );
}
