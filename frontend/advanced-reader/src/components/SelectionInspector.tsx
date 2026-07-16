import { isPersistableSelection } from "../annotations/ui";
import type { TextSelectionEvent } from "../selection/types";
import type {
  PageLabel,
  VisualAnnotationKind,
} from "../types/api";

interface SelectionInspectorProps {
  selection: TextSelectionEvent | null;
  pageLabel: PageLabel | null;
  persistenceEnabled: boolean;
  onChoose(kind: VisualAnnotationKind): void;
  onClear(): void;
}

function selectionStatus(selection: TextSelectionEvent): string {
  if (selection.geometry_status === "cross_page") return "Selección multipágina";
  if (selection.geometry_status === "unresolved") return "Página no resuelta";
  return "Texto seleccionado · Sin guardar";
}

export function SelectionInspector({
  selection,
  pageLabel,
  persistenceEnabled,
  onChoose,
  onClear,
}: SelectionInspectorProps) {
  if (selection === null) return null;
  return (
    <section className="inspector-card" aria-labelledby="selection-inspector-heading">
      <div className="eyebrow">Texto seleccionado</div>
      <h2 id="selection-inspector-heading">{selectionStatus(selection)}</h2>
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
            <div><dt>Página</dt><dd>{pageLabel?.display_label ?? `PDF ${selection.pdf_page ?? "—"}`}</dd></div>
          </dl>
          <div className="button-row">
            {persistenceEnabled && isPersistableSelection(selection) && (
              <>
                <button type="button" onClick={() => onChoose("highlight")}>Highlight</button>
                <button type="button" onClick={() => onChoose("underline")}>Underline</button>
              </>
            )}
            <button type="button" onClick={onClear}>Cancelar</button>
          </div>
      </>
      {!persistenceEnabled && (
        <p className="future-note">
          Guardar no está disponible. Revisa la configuración.
        </p>
      )}
    </section>
  );
}
