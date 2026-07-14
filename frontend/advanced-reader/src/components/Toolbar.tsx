import { useEffect, useState } from "react";

import type { SearchDirection, SearchStatus } from "../pdf/types";
import type { ReaderCapabilities } from "../types/api";

interface ToolbarProps {
  ready: boolean;
  capabilities: ReaderCapabilities;
  sidebarOpen: boolean;
  inspectorOpen: boolean;
  currentPage: number;
  totalPages: number;
  zoomPercent: number;
  rotation: number;
  searchQuery: string;
  searchStatus: SearchStatus;
  searchCurrent: number;
  searchTotal: number;
  caseSensitive: boolean;
  entireWord: boolean;
  saving: boolean;
  onToggleSidebar(): void;
  onToggleInspector(): void;
  onFirstPage(): void;
  onPreviousPage(): void;
  onNextPage(): void;
  onLastPage(): void;
  onGoToPage(page: number): void;
  onZoomOut(): void;
  onZoomIn(): void;
  onFitWidth(): void;
  onFitPage(): void;
  onActualSize(): void;
  onRotateCounterclockwise(): void;
  onRotateClockwise(): void;
  onSearchQuery(query: string): void;
  onSearch(direction: SearchDirection, again: boolean): void;
  onCaseSensitive(value: boolean): void;
  onEntireWord(value: boolean): void;
  onSavePosition(): void;
}

function searchLabel(status: SearchStatus, current: number, total: number): string {
  if (status === "pending") return "Buscando…";
  if (status === "not_found") return "Sin resultados";
  if ((status === "found" || status === "wrapped") && total > 0) {
    return `${current} de ${total}`;
  }
  return "";
}

export function Toolbar(props: ToolbarProps) {
  const [pageDraft, setPageDraft] = useState(String(props.currentPage));

  useEffect(() => setPageDraft(String(props.currentPage)), [props.currentPage]);

  const submitPage = () => {
    const value = Number(pageDraft);
    if (Number.isInteger(value)) {
      props.onGoToPage(value);
    } else {
      setPageDraft(String(props.currentPage));
    }
  };

  return (
    <header className="reader-toolbar" aria-label="Controles del lector PDF">
      <div className="toolbar-group toolbar-layout-controls">
        <button
          type="button"
          aria-label="Mostrar u ocultar miniaturas"
          aria-pressed={props.sidebarOpen}
          disabled={!props.capabilities.thumbnails}
          onClick={props.onToggleSidebar}
        >
          Miniaturas
        </button>
        <button
          type="button"
          aria-label="Mostrar u ocultar inspector"
          aria-pressed={props.inspectorOpen}
          onClick={props.onToggleInspector}
        >
          Inspector
        </button>
      </div>

      <div className="toolbar-group" aria-label="Navegación de páginas">
        <button
          type="button"
          aria-label="Primera página"
          disabled={!props.ready || !props.capabilities.page_navigation || props.currentPage <= 1}
          onClick={props.onFirstPage}
        >
          Primera
        </button>
        <button
          type="button"
          aria-label="Página anterior"
          disabled={!props.ready || !props.capabilities.page_navigation || props.currentPage <= 1}
          onClick={props.onPreviousPage}
        >
          Anterior
        </button>
        <form
          className="page-control"
          onSubmit={(event) => {
            event.preventDefault();
            submitPage();
          }}
        >
          <label htmlFor="pdf-page-input">PDF page</label>
          <input
            id="pdf-page-input"
            aria-label="PDF page"
            inputMode="numeric"
            value={pageDraft}
            disabled={!props.ready || !props.capabilities.page_navigation}
            onChange={(event) => setPageDraft(event.target.value)}
            onBlur={submitPage}
          />
          <span aria-label={`Total de páginas: ${props.totalPages}`}>/ {props.totalPages || "—"}</span>
        </form>
        <button
          type="button"
          aria-label="Página siguiente"
          disabled={!props.ready || !props.capabilities.page_navigation || props.currentPage >= props.totalPages}
          onClick={props.onNextPage}
        >
          Siguiente
        </button>
        <button
          type="button"
          aria-label="Última página"
          disabled={!props.ready || !props.capabilities.page_navigation || props.currentPage >= props.totalPages}
          onClick={props.onLastPage}
        >
          Última
        </button>
      </div>

      <div className="toolbar-group" aria-label="Zoom y rotación">
        <button type="button" aria-label="Reducir zoom" disabled={!props.ready || !props.capabilities.zoom} onClick={props.onZoomOut}>
          −
        </button>
        <output aria-label="Zoom actual">{props.zoomPercent}%</output>
        <button type="button" aria-label="Aumentar zoom" disabled={!props.ready || !props.capabilities.zoom} onClick={props.onZoomIn}>
          +
        </button>
        <button type="button" disabled={!props.ready || !props.capabilities.zoom} onClick={props.onFitWidth}>
          Ajustar ancho
        </button>
        <button type="button" disabled={!props.ready || !props.capabilities.zoom} onClick={props.onFitPage}>
          Ajustar página
        </button>
        <button type="button" disabled={!props.ready || !props.capabilities.zoom} onClick={props.onActualSize}>
          Tamaño real
        </button>
        <button
          type="button"
          aria-label="Rotar a la izquierda"
          disabled={!props.ready || !props.capabilities.rotate}
          onClick={props.onRotateCounterclockwise}
        >
          ↶
        </button>
        <button
          type="button"
          aria-label="Rotar a la derecha"
          disabled={!props.ready || !props.capabilities.rotate}
          onClick={props.onRotateClockwise}
        >
          ↷
        </button>
        <output aria-label="Rotación actual">{props.rotation}°</output>
      </div>

      <div className="toolbar-group search-controls" role="search">
        <label htmlFor="pdf-search-input">Buscar</label>
        <input
          id="pdf-search-input"
          aria-label="Buscar en el PDF"
          type="search"
          value={props.searchQuery}
          maxLength={256}
          disabled={!props.ready || !props.capabilities.text_search}
          onChange={(event) => props.onSearchQuery(event.target.value)}
          onKeyDown={(event) => {
            if (event.key === "Enter") {
              event.preventDefault();
              props.onSearch("next", false);
            }
          }}
        />
        <button
          type="button"
          aria-label="Coincidencia anterior"
          disabled={!props.ready || !props.capabilities.text_search || !props.searchQuery.trim()}
          onClick={() => props.onSearch("previous", true)}
        >
          ↑
        </button>
        <button
          type="button"
          aria-label="Coincidencia siguiente"
          disabled={!props.ready || !props.capabilities.text_search || !props.searchQuery.trim()}
          onClick={() => props.onSearch("next", true)}
        >
          ↓
        </button>
        <label className="check-control">
          <input
            type="checkbox"
            checked={props.caseSensitive}
            disabled={!props.ready || !props.capabilities.text_search}
            onChange={(event) => props.onCaseSensitive(event.target.checked)}
          />
          Aa
        </label>
        <label className="check-control">
          <input
            type="checkbox"
            checked={props.entireWord}
            disabled={!props.ready || !props.capabilities.text_search}
            onChange={(event) => props.onEntireWord(event.target.checked)}
          />
          Palabra completa
        </label>
        <output className="search-result" aria-live="polite">
          {searchLabel(props.searchStatus, props.searchCurrent, props.searchTotal)}
        </output>
      </div>

      <div className="toolbar-group toolbar-save">
        <button
          type="button"
          className="primary-button"
          disabled={!props.ready || props.saving}
          onClick={props.onSavePosition}
        >
          {props.saving ? "Guardando…" : "Guardar posición"}
        </button>
      </div>
    </header>
  );
}
