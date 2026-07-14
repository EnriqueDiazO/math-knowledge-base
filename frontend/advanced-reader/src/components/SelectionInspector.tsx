import { useState } from "react";

import {
  VISUAL_ANNOTATION_COLORS,
  isPersistableSelection,
} from "../annotations/ui";
import type { TextSelectionEvent } from "../selection/types";
import type {
  PageLabel,
  VisualAnnotationColor,
  VisualAnnotationKind,
} from "../types/api";

interface SelectionInspectorProps {
  selection: TextSelectionEvent | null;
  pageLabel: PageLabel | null;
  persistenceEnabled: boolean;
  color: VisualAnnotationColor;
  onColor(color: VisualAnnotationColor): void;
  onChoose(kind: VisualAnnotationKind): void;
  onClear(): void;
}

function selectionStatus(selection: TextSelectionEvent | null): string {
  if (selection === null) return "Sin selección";
  if (selection.geometry_status === "cross_page") return "Selección multipágina";
  if (selection.geometry_status === "unresolved") return "Página no resuelta";
  return "Selección válida de una página";
}

export function SelectionInspector({
  selection,
  pageLabel,
  persistenceEnabled,
  color,
  onColor,
  onChoose,
  onClear,
}: SelectionInspectorProps) {
  const [technicalOpen, setTechnicalOpen] = useState(false);

  return (
    <section className="inspector-card" aria-labelledby="selection-inspector-heading">
      <div className="eyebrow">Selección actual</div>
      <h2 id="selection-inspector-heading">{selectionStatus(selection)}</h2>
      {selection === null ? (
        <p className="muted">Selecciona texto dentro de una página para inspeccionar su geometría efímera.</p>
      ) : (
        <>
          {selection.cross_page && (
            <p className="warning-banner" role="status">
              La selección cruza páginas. Se muestra el texto, pero no se genera geometría utilizable.
            </p>
          )}
          {selection.geometry_status === "unresolved" && (
            <p className="warning-banner" role="status">
              No se pudo resolver una única página; la geometría fue descartada.
            </p>
          )}
          <blockquote className="selection-text">{selection.selected_text}</blockquote>
          <dl className="metadata-list compact">
            <div><dt>PDF page</dt><dd>{selection.pdf_page ?? "—"}</dd></div>
            <div><dt>Book page</dt><dd>{pageLabel?.book_page_label ?? "—"}</dd></div>
            <div><dt>Rectángulos</dt><dd>{selection.rects_normalized.length}</dd></div>
          </dl>
          <div className="button-row">
            {persistenceEnabled && isPersistableSelection(selection) && (
              <>
                <button type="button" onClick={() => onChoose("highlight")}>Highlight</button>
                <button type="button" onClick={() => onChoose("underline")}>Underline</button>
                <select
                  aria-label="Color de la marca en inspector"
                  value={color}
                  onChange={(event) => onColor(event.target.value as VisualAnnotationColor)}
                >
                  {VISUAL_ANNOTATION_COLORS.map((value) => (
                    <option key={value} value={value}>{value}</option>
                  ))}
                </select>
              </>
            )}
            <button type="button" onClick={onClear}>Limpiar selección</button>
            <button type="button" onClick={() => setTechnicalOpen((value) => !value)}>
              Mostrar detalles técnicos
            </button>
          </div>
          {technicalOpen && (
            import.meta.env.DEV ? (
              <pre className="technical-selection">{JSON.stringify(selection, null, 2)}</pre>
            ) : (
              <p className="muted">El payload técnico completo sólo se muestra en modo desarrollo.</p>
            )
          )}
        </>
      )}
      {!persistenceEnabled && (
        <p className="future-note">
          Inicializa Notes &amp; Evidence en Maintenance para guardar marcas visuales.
        </p>
      )}
    </section>
  );
}
