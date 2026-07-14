import { useState } from "react";

import type { TextSelectionEvent } from "../selection/types";
import type { PageLabel } from "../types/api";

interface SelectionInspectorProps {
  selection: TextSelectionEvent | null;
  pageLabel: PageLabel | null;
  onClear(): void;
}

function selectionStatus(selection: TextSelectionEvent | null): string {
  if (selection === null) return "Sin selección";
  if (selection.geometry_status === "cross_page") return "Selección multipágina";
  if (selection.geometry_status === "unresolved") return "Página no resuelta";
  return "Selección válida de una página";
}

export function SelectionInspector({ selection, pageLabel, onClear }: SelectionInspectorProps) {
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
      <p className="future-note">Visual annotation persistence will be added in a later phase.</p>
    </section>
  );
}
