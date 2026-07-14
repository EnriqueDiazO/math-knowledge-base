import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import {
  ReaderApiError,
  advancedReaderApi,
  documentIdFromSearch,
} from "../api/client";
import type { AdvancedReaderApi } from "../api/client";
import { DocumentInspector } from "../components/DocumentInspector";
import { ReaderStatus } from "../components/ReaderStatus";
import { SelectionInspector } from "../components/SelectionInspector";
import { Toolbar } from "../components/Toolbar";
import type {
  PdfReaderController,
  PdfReaderControllerFactory,
  SearchDirection,
  SearchStatus,
} from "../pdf/types";
import { limitSearchQuery, normalizeSearchQuery } from "../pdf/search";
import type { TextSelectionEvent } from "../selection/types";
import type { DocumentMetadata, PageLabel } from "../types/api";
import type {
  AdvancedReaderEventV1,
  PublicReaderErrorCode,
  ReadingStatus,
  RotationChangedEventV1,
  SearchResultEventV1,
  SelectionClearReason,
  ZoomChangedEventV1,
} from "../types/events";

type Phase = "loading_metadata" | "loading_pdf" | "ready" | "error";
type SaveStatus = "idle" | "saving" | "saved" | "error";

interface AppError {
  code: string;
  title: string;
  message: string;
}

export interface AdvancedReaderAppProps {
  api?: AdvancedReaderApi;
  controllerFactory: PdfReaderControllerFactory;
  search?: string;
  onEvent?: (event: AdvancedReaderEventV1) => void;
}

const PUBLIC_ERROR_CODES = new Set<PublicReaderErrorCode>([
  "invalid_document_id",
  "document_not_found",
  "document_archived",
  "document_not_pdf",
  "integrity_error",
  "blob_missing",
  "invalid_range",
  "multiple_ranges_not_supported",
  "page_invalid",
  "database_unavailable",
  "frontend_not_built",
  "internal_error",
  "api_unavailable",
  "pdfjs_load_error",
  "unsupported_document",
]);

const READING_STATUSES = new Set<ReadingStatus>([
  "unread",
  "in_progress",
  "completed",
  "deferred",
]);

function publicErrorCode(value: string): PublicReaderErrorCode {
  return PUBLIC_ERROR_CODES.has(value as PublicReaderErrorCode)
    ? (value as PublicReaderErrorCode)
    : "internal_error";
}

function readingStatus(value: string): ReadingStatus {
  return READING_STATUSES.has(value as ReadingStatus)
    ? (value as ReadingStatus)
    : "in_progress";
}

function safeRotation(value: number): RotationChangedEventV1["rotation"] {
  return [0, 90, 180, 270].includes(value)
    ? (value as RotationChangedEventV1["rotation"])
    : 0;
}

function safeTotalPageCount(value: number): number {
  return Number.isSafeInteger(value) && value >= 1 ? value : 1;
}

function safePdfPage(value: number | null, totalPages: number): number {
  const page = Number.isSafeInteger(value) && value !== null ? value : 1;
  return Math.min(totalPages, Math.max(1, page));
}

function boundedBookPageLabel(value: string | null): string | null {
  if (value === null) return null;
  return Array.from(value.replace(/\s+/gu, " ").trim()).slice(0, 64).join("");
}

function searchResultPayload(
  status: SearchStatus,
  current: number,
  total: number,
): Pick<SearchResultEventV1, "status" | "current_match" | "total_matches"> {
  if (status === "pending") {
    return { status: "searching", current_match: null, total_matches: null };
  }
  if (status === "idle") {
    return { status: "cancelled", current_match: null, total_matches: null };
  }
  if (status === "not_found") {
    return { status: "not_found", current_match: 0, total_matches: 0 };
  }
  const safeTotal = Number.isInteger(total) && total > 0 ? total : null;
  const safeCurrent =
    safeTotal !== null && Number.isInteger(current) && current >= 1 && current <= safeTotal
      ? current
      : null;
  return { status: "found", current_match: safeCurrent, total_matches: safeTotal };
}

function emitLocalEvent(
  callback: ((event: AdvancedReaderEventV1) => void) | undefined,
  event: AdvancedReaderEventV1,
): void {
  try {
    callback?.(event);
  } catch {
    // An optional local observer cannot break reading or create a logging side channel.
  }
}

function fallbackPageLabel(page: number): PageLabel {
  return { pdf_page: page, book_page_label: null, display_label: `PDF page ${page}` };
}

function appError(error: unknown): AppError {
  const code = error instanceof ReaderApiError ? error.code : "internal_error";
  if (code === "invalid_document_id") {
    return {
      code,
      title: "Document inválido",
      message: "Abre el lector desde Reading Space con un identificador válido.",
    };
  }
  if (code === "document_not_pdf") {
    return {
      code,
      title: "Document no compatible",
      message: "Advanced Reader sólo abre Documents PDF; no navega recursos web.",
    };
  }
  if (code === "integrity_error" || code === "blob_missing") {
    return {
      code,
      title: "No se pudo verificar el PDF",
      message: "La comprobación de integridad local bloqueó la apertura del archivo.",
    };
  }
  if (code === "api_unavailable" || code === "database_unavailable") {
    return {
      code,
      title: "API local no disponible",
      message: "Comprueba que Advanced Reader y la base configurada estén disponibles.",
    };
  }
  if (code === "document_archived") {
    return {
      code,
      title: "Document archivado",
      message: "Reactiva el Document desde MathMongo antes de abrirlo.",
    };
  }
  return {
    code,
    title: "No se pudo abrir el lector",
    message: "La solicitud local falló de forma segura. Puedes reintentar.",
  };
}

export function AdvancedReaderApp({
  api = advancedReaderApi,
  controllerFactory,
  search = window.location.search,
  onEvent,
}: AdvancedReaderAppProps) {
  const documentId = useMemo(() => documentIdFromSearch(search), [search]);
  const [retryKey, setRetryKey] = useState(0);
  const [phase, setPhase] = useState<Phase>("loading_metadata");
  const [error, setError] = useState<AppError | null>(null);
  const [metadata, setMetadata] = useState<DocumentMetadata | null>(null);
  const [currentPage, setCurrentPage] = useState(1);
  const [totalPages, setTotalPages] = useState(0);
  const [pageLabel, setPageLabel] = useState<PageLabel>(fallbackPageLabel(1));
  const [zoomPercent, setZoomPercent] = useState(100);
  const [rotation, setRotation] = useState(0);
  const [sidebarOpen, setSidebarOpen] = useState(true);
  const [inspectorOpen, setInspectorOpen] = useState(true);
  const [searchQuery, setSearchQuery] = useState("");
  const [searchStatus, setSearchStatus] = useState<SearchStatus>("idle");
  const [searchCurrent, setSearchCurrent] = useState(0);
  const [searchTotal, setSearchTotal] = useState(0);
  const [caseSensitive, setCaseSensitive] = useState(false);
  const [entireWord, setEntireWord] = useState(false);
  const [selection, setSelection] = useState<TextSelectionEvent | null>(null);
  const [selectionPageLabel, setSelectionPageLabel] = useState<PageLabel | null>(null);
  const [saveStatus, setSaveStatus] = useState<SaveStatus>("idle");

  const containerRef = useRef<HTMLDivElement>(null);
  const viewerRef = useRef<HTMLDivElement>(null);
  const thumbnailsRef = useRef<HTMLDivElement>(null);
  const controllerRef = useRef<PdfReaderController | null>(null);
  const totalPagesRef = useRef(0);
  const selectionRef = useRef<TextSelectionEvent | null>(null);
  const zoomModeRef = useRef<ZoomChangedEventV1["mode"]>("fit_width");
  const onEventRef = useRef(onEvent);
  onEventRef.current = onEvent;
  const emitEvent = useCallback(
    (event: AdvancedReaderEventV1) => emitLocalEvent(onEventRef.current, event),
    [],
  );

  useEffect(() => {
    if (documentId === null) {
      setPhase("error");
      setError(appError(new ReaderApiError("invalid_document_id", "Invalid Document.")));
      return;
    }
    const abortController = new AbortController();
    setPhase("loading_metadata");
    setError(null);
    setMetadata(null);
    setSelection(null);
    setSelectionPageLabel(null);
    setSearchQuery("");
    setSearchStatus("idle");
    setSearchCurrent(0);
    setSearchTotal(0);
    api.getMetadata(documentId, abortController.signal)
      .then((value) => {
        if (!abortController.signal.aborted) {
          setMetadata(value);
          const initialPage = value.reading_state.current_page ?? 1;
          setCurrentPage(initialPage);
          setPageLabel(value.page_label ?? fallbackPageLabel(initialPage));
          setPhase("loading_pdf");
        }
      })
      .catch((reason: unknown) => {
        if (!abortController.signal.aborted) {
          const visibleError = appError(reason);
          setError(visibleError);
          setPhase("error");
          emitEvent({
            schema_version: 1,
            event_type: "document_load_failed",
            document_id: documentId,
            version_id: null,
            error_code: publicErrorCode(visibleError.code),
          });
        }
      });
    return () => abortController.abort();
  }, [api, documentId, emitEvent, retryKey]);

  useEffect(() => {
    if (metadata !== null && !metadata.capabilities.thumbnails) {
      setSidebarOpen(false);
    }
  }, [metadata]);

  useEffect(() => {
    if (
      metadata === null ||
      containerRef.current === null ||
      viewerRef.current === null ||
      thumbnailsRef.current === null
    ) {
      return;
    }
    const controller = controllerFactory();
    controllerRef.current = controller;
    setSelection(null);
    setSelectionPageLabel(null);
    let pageLabelController: AbortController | null = null;
    let selectionLabelController: AbortController | null = null;

    const clearSelectionEvent = (reason: SelectionClearReason) => {
      const hadSelection = selectionRef.current !== null;
      selectionRef.current = null;
      setSelection(null);
      setSelectionPageLabel(null);
      selectionLabelController?.abort();
      selectionLabelController = null;
      if (hadSelection || reason === "empty") {
        emitEvent({
          schema_version: 1,
          event_type: "selection_cleared",
          document_id: metadata.document_id,
          version_id: metadata.version.version_id,
          reason,
        });
      }
    };

    const loadPageLabel = (pdfPage: number) => {
      pageLabelController?.abort();
      const requestController = new AbortController();
      pageLabelController = requestController;
      setPageLabel(fallbackPageLabel(pdfPage));
      void api.getPageLabel(metadata.document_id, pdfPage, requestController.signal)
        .then((label) => setPageLabel(label))
        .catch(() => undefined);
    };

    const loadSelectionLabel = (value: TextSelectionEvent | null) => {
      selectionLabelController?.abort();
      setSelectionPageLabel(null);
      if (value?.pdf_page === null || value === null) return;
      const requestController = new AbortController();
      selectionLabelController = requestController;
      void api.getPageLabel(
        metadata.document_id,
        value.pdf_page,
        requestController.signal,
      ).then((label) => setSelectionPageLabel(label)).catch(() => undefined);
    };

    const updateSelection = (
      value: TextSelectionEvent | null,
      reason: SelectionClearReason = "empty",
    ) => {
      if (value === null) {
        clearSelectionEvent(reason);
        return;
      }
      selectionRef.current = value;
      setSelection(value);
      loadSelectionLabel(value);
      emitEvent(value);
    };

    void controller.mount({
      container: containerRef.current,
      viewer: viewerRef.current,
      thumbnails: thumbnailsRef.current,
      pdfUrl: api.pdfUrl(metadata.document_id),
      documentId: metadata.document_id,
      versionId: metadata.version.version_id,
      initialPage: metadata.reading_state.current_page ?? 1,
      handlers: {
        onReady(pages) {
          const safePages = safeTotalPageCount(pages);
          const initialPage = safePdfPage(metadata.reading_state.current_page, safePages);
          totalPagesRef.current = safePages;
          setTotalPages(safePages);
          setPhase("ready");
          emitEvent({
            schema_version: 1,
            event_type: "document_loaded",
            document_id: metadata.document_id,
            version_id: metadata.version.version_id,
            total_pages: safePages,
            initial_pdf_page: initialPage,
          });
        },
        onPageChanged(pdfPage, origin) {
          clearSelectionEvent("page_change");
          const pages = safeTotalPageCount(totalPagesRef.current);
          const safePage = safePdfPage(pdfPage, pages);
          setCurrentPage(safePage);
          setSaveStatus("idle");
          loadPageLabel(safePage);
          const initialLabel = metadata.page_label?.pdf_page === safePage
            ? boundedBookPageLabel(metadata.page_label.book_page_label)
            : null;
          emitEvent({
            schema_version: 1,
            event_type: "page_changed",
            document_id: metadata.document_id,
            version_id: metadata.version.version_id,
            pdf_page: safePage,
            total_pages: pages,
            book_page_label: initialLabel,
            origin,
          });
        },
        onZoomChanged(scale) {
          const safeScale = Number.isFinite(scale)
            ? Math.min(5, Math.max(0.25, scale))
            : 1;
          setZoomPercent(Math.round(safeScale * 100));
          emitEvent({
            schema_version: 1,
            event_type: "zoom_changed",
            document_id: metadata.document_id,
            version_id: metadata.version.version_id,
            scale: safeScale,
            mode: zoomModeRef.current,
          });
        },
        onRotationChanged(value, direction) {
          clearSelectionEvent("rotation_change");
          const safeValue = safeRotation(value);
          setRotation(safeValue);
          emitEvent({
            schema_version: 1,
            event_type: "rotation_changed",
            document_id: metadata.document_id,
            version_id: metadata.version.version_id,
            rotation: safeValue,
            direction,
          });
        },
        onSearchChanged(update) {
          setSearchStatus(update.status);
          setSearchCurrent(update.current);
          setSearchTotal(update.total);
          emitEvent({
            schema_version: 1,
            event_type: "search_result",
            document_id: metadata.document_id,
            version_id: metadata.version.version_id,
            ...searchResultPayload(update.status, update.current, update.total),
          });
        },
        onSelectionChanged(value, reason) {
          updateSelection(value, reason);
        },
        onError() {
          clearSelectionEvent("load_failure");
          setError(appError(new ReaderApiError("pdfjs_load_error", "PDF load failed.")));
          setPhase("error");
          emitEvent({
            schema_version: 1,
            event_type: "document_load_failed",
            document_id: metadata.document_id,
            version_id: metadata.version.version_id,
            error_code: "pdfjs_load_error",
          });
        },
      },
    });

    return () => {
      pageLabelController?.abort();
      selectionLabelController?.abort();
      if (selectionRef.current !== null) {
        selectionRef.current = null;
        emitEvent({
          schema_version: 1,
          event_type: "selection_cleared",
          document_id: metadata.document_id,
          version_id: metadata.version.version_id,
          reason: "unmount",
        });
      }
      totalPagesRef.current = 0;
      controller.destroy();
      if (controllerRef.current === controller) controllerRef.current = null;
    };
  }, [api, controllerFactory, emitEvent, metadata]);

  const ready = phase === "ready";
  const executeSearch = (direction: SearchDirection, again: boolean) => {
    if (metadata === null) return;
    const query = normalizeSearchQuery(searchQuery);
    setSearchQuery(query);
    if (query) {
      emitEvent({
        schema_version: 1,
        event_type: "search_started",
        document_id: metadata.document_id,
        version_id: metadata.version.version_id,
        query,
        case_sensitive: caseSensitive,
        whole_words: entireWord,
        direction,
      });
    }
    controllerRef.current?.search(
      query,
      direction,
      { caseSensitive, entireWord },
      again,
    );
  };

  const savePosition = async () => {
    if (metadata === null || saveStatus === "saving") return;
    const savedPage = currentPage;
    setSaveStatus("saving");
    try {
      const result = await api.savePage(metadata.document_id, savedPage);
      setSaveStatus("saved");
      emitEvent({
        schema_version: 1,
        event_type: "reading_position_saved",
        document_id: metadata.document_id,
        version_id: metadata.version.version_id,
        pdf_page: savedPage,
        reading_status: readingStatus(result.status),
      });
    } catch {
      setSaveStatus("error");
    }
  };

  if (phase === "error" || documentId === null) {
    const visibleError = error ?? appError(new ReaderApiError("invalid_document_id", "Invalid."));
    return (
      <ReaderStatus
        kind="error"
        title={visibleError.title}
        message={visibleError.message}
        onRetry={documentId === null ? undefined : () => setRetryKey((value) => value + 1)}
      />
    );
  }
  if (metadata === null) {
    return (
      <ReaderStatus
        kind="loading"
        title="Preparando el lector"
        message="Validando el Document y su integridad local…"
      />
    );
  }

  return (
    <div
      className={`reader-app${sidebarOpen ? " has-sidebar" : ""}${inspectorOpen ? " has-inspector" : ""}`}
      data-phase={phase}
    >
      <Toolbar
        ready={ready}
        capabilities={metadata.capabilities}
        sidebarOpen={sidebarOpen}
        inspectorOpen={inspectorOpen}
        currentPage={currentPage}
        totalPages={totalPages}
        zoomPercent={zoomPercent}
        rotation={rotation}
        searchQuery={searchQuery}
        searchStatus={searchStatus}
        searchCurrent={searchCurrent}
        searchTotal={searchTotal}
        caseSensitive={caseSensitive}
        entireWord={entireWord}
        saving={saveStatus === "saving"}
        onToggleSidebar={() => setSidebarOpen((value) => !value)}
        onToggleInspector={() => setInspectorOpen((value) => !value)}
        onFirstPage={() => controllerRef.current?.goToPage(1, "toolbar")}
        onPreviousPage={() => controllerRef.current?.previousPage()}
        onNextPage={() => controllerRef.current?.nextPage()}
        onLastPage={() => controllerRef.current?.goToPage(totalPages, "toolbar")}
        onGoToPage={(page) => controllerRef.current?.goToPage(page, "page_input")}
        onZoomOut={() => {
          zoomModeRef.current = "custom";
          controllerRef.current?.zoomOut();
        }}
        onZoomIn={() => {
          zoomModeRef.current = "custom";
          controllerRef.current?.zoomIn();
        }}
        onFitWidth={() => {
          zoomModeRef.current = "fit_width";
          controllerRef.current?.setScaleMode("page-width");
        }}
        onFitPage={() => {
          zoomModeRef.current = "fit_page";
          controllerRef.current?.setScaleMode("page-fit");
        }}
        onActualSize={() => {
          zoomModeRef.current = "actual_size";
          controllerRef.current?.setScaleMode("page-actual");
        }}
        onRotateCounterclockwise={() => controllerRef.current?.rotateCounterclockwise()}
        onRotateClockwise={() => controllerRef.current?.rotateClockwise()}
        onSearchQuery={(query) => setSearchQuery(limitSearchQuery(query))}
        onSearch={executeSearch}
        onCaseSensitive={setCaseSensitive}
        onEntireWord={setEntireWord}
        onSavePosition={() => void savePosition()}
      />

      <div className="reader-body">
        <aside className="thumbnail-sidebar" aria-label="Miniaturas PDF" aria-hidden={!sidebarOpen}>
          <div className="panel-heading">
            <span>Pages</span><span>{totalPages || "—"}</span>
          </div>
          <div className="thumbnail-scroll">
            <div ref={thumbnailsRef} className="thumbnail-list" data-testid="thumbnail-rail" />
          </div>
        </aside>

        <main className="pdf-stage" aria-label="Documento PDF">
          {phase === "loading_pdf" && (
            <div className="pdf-loading" role="status">Renderizando PDF con PDF.js…</div>
          )}
          <div ref={containerRef} id="viewerContainer" tabIndex={0}>
            <div ref={viewerRef} id="viewer" className="pdfViewer" />
          </div>
        </main>

        <aside className="reader-inspector" aria-label="Inspector" aria-hidden={!inspectorOpen}>
          <DocumentInspector metadata={metadata} currentPage={currentPage} pageLabel={pageLabel} />
          <SelectionInspector
            selection={selection}
            pageLabel={selectionPageLabel}
            onClear={() => controllerRef.current?.clearSelection("user")}
          />
          {saveStatus === "saved" && <p className="save-feedback success" role="status">Posición guardada.</p>}
          {saveStatus === "error" && <p className="save-feedback error" role="alert">No se pudo guardar la posición.</p>}
        </aside>
      </div>
    </div>
  );
}
