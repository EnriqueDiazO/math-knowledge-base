import type { TextSelectionEvent } from "../selection/types";
import { VISUAL_ANNOTATION_COLORS } from "../annotations/ui";
import type {
  PageLabel,
  VisualAnnotationColor,
  VisualAnnotationKind,
} from "../types/api";

export interface VisualAnnotationDraft {
  annotationId: string;
  kind: VisualAnnotationKind;
  color: VisualAnnotationColor;
  body: string;
  tagsText: string;
}

interface VisualAnnotationConfirmationProps {
  draft: VisualAnnotationDraft;
  selection: TextSelectionEvent;
  pageLabel: PageLabel | null;
  saving: boolean;
  error: string | null;
  onChange(draft: VisualAnnotationDraft): void;
  onSave(): void;
  onCancel(): void;
}

export function VisualAnnotationConfirmation({
  draft,
  selection,
  pageLabel,
  saving,
  error,
  onChange,
  onSave,
  onCancel,
}: VisualAnnotationConfirmationProps) {
  return (
    <section className="inspector-card visual-confirmation" aria-labelledby="visual-confirm-heading">
      <div className="eyebrow">Confirmar marca visual</div>
      <h2 id="visual-confirm-heading">Guardar explícitamente</h2>
      <div className="visual-form-grid">
        <label>
          Tipo
          <select
            aria-label="Tipo de marca"
            value={draft.kind}
            disabled={saving}
            onChange={(event) => onChange({
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
            aria-label="Color de la marca a guardar"
            value={draft.color}
            disabled={saving}
            onChange={(event) => onChange({
              ...draft,
              color: event.target.value as VisualAnnotationColor,
            })}
          >
            {VISUAL_ANNOTATION_COLORS.map((value) => (
              <option key={value} value={value}>{value}</option>
            ))}
          </select>
        </label>
      </div>
      <blockquote className="selection-text">{selection.selected_text}</blockquote>
      <dl className="metadata-list compact">
        <div><dt>PDF page</dt><dd>{selection.pdf_page}</dd></div>
        <div><dt>Book page</dt><dd>{pageLabel?.book_page_label ?? "—"}</dd></div>
      </dl>
      <label className="visual-field">
        Comentario opcional
        <textarea
          aria-label="Comentario de la marca"
          rows={3}
          maxLength={50_000}
          value={draft.body}
          disabled={saving}
          onChange={(event) => onChange({ ...draft, body: event.target.value })}
        />
      </label>
      <label className="visual-field">
        Tags, separados por comas
        <input
          aria-label="Tags de la marca"
          type="text"
          maxLength={5_000}
          value={draft.tagsText}
          disabled={saving}
          onChange={(event) => onChange({ ...draft, tagsText: event.target.value })}
        />
      </label>
      {error !== null && <p className="save-feedback error" role="alert">{error}</p>}
      <div className="button-row">
        <button
          type="button"
          className="primary-button"
          disabled={saving}
          onClick={onSave}
        >
          {saving ? "Guardando…" : "Guardar marca"}
        </button>
        <button type="button" disabled={saving} onClick={onCancel}>Cancelar</button>
      </div>
    </section>
  );
}
