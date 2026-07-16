import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import {
  ReaderApiError,
  advancedReaderApi,
  documentIdFromSearch,
} from "../api/client";
import type { AdvancedReaderApi } from "../api/client";
import {
  isPersistableSelection,
  mergeVisualAnnotationSnapshots,
  parseVisualAnnotationTags,
} from "../annotations/ui";
import { ConceptLinkWizard } from "../concepts/ConceptLinkWizard";
import { ConceptPanels } from "../concepts/ConceptPanels";
import { ReaderStatus } from "../components/ReaderStatus";
import { SelectionActionToolbar } from "../components/SelectionActionToolbar";
import { SelectionInspector } from "../components/SelectionInspector";
import { Toolbar } from "../components/Toolbar";
import {
  VisualAnnotationConfirmation,
  type VisualAnnotationDraft,
} from "../components/VisualAnnotationConfirmation";
import {
  VisualAnnotationsPanel,
  type VisualAnnotationFilters,
} from "../components/VisualAnnotationsPanel";
import type { VisualAnnotationRenderItem } from "../annotations/types";
import type {
  PdfReaderController,
  PdfReaderControllerFactory,
  SearchDirection,
  SearchStatus,
} from "../pdf/types";
import { limitSearchQuery, normalizeSearchQuery } from "../pdf/search";
import type { TextSelectionEvent } from "../selection/types";
import type {
  CreateVisualAnnotation,
  ConceptEvidence,
  DocumentMetadata,
  DocumentConceptGroup,
  PageLabel,
  UpdateVisualAnnotation,
  UnlinkedVisualAnnotation,
  VisualAnnotation,
  VisualAnnotationKind,
} from "../types/api";
import type {
  AdvancedReaderEventV1,
  PublicReaderErrorCode,
  ReadingStatus,
  RotationChangedEventV1,
  SearchResultEventV1,
  SelectionClearReason,
  ZoomChangedEventV1,
} from "../types/events";

type Phase = "loading_metadata" | "loading_pdf" | "ready" | "page_render_failed" | "error";
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
  "page_render_failed",
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

function renderVisualAnnotation(annotation: VisualAnnotation): VisualAnnotationRenderItem {
  return {
    annotation_id: annotation.annotation_id,
    kind: annotation.kind,
    status: annotation.status,
    pdf_page: annotation.pdf_page,
    color_label: annotation.color_label ?? "yellow",
    visual_status: annotation.visual_status,
    visual_anchor: annotation.visual_anchor,
  };
}

function newVisualAnnotationId(): string | null {
  if (typeof window.crypto?.randomUUID !== "function") return null;
  return `ann_${window.crypto.randomUUID()}`;
}

function visualWriteEnabled(metadata: DocumentMetadata | null): boolean {
  return metadata !== null &&
    metadata.status === "active" &&
    metadata.capabilities.persistent_highlights &&
    metadata.capabilities.persistent_underlines &&
    metadata.capabilities.visual_annotation_editing &&
    metadata.capabilities.visual_annotation_archiving;
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
  if (code === "page_render_failed") {
    return {
      code,
      title: "No se pudo renderizar la página",
      message: "PDF.js cargó el Document, pero no produjo píxeles visibles.",
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
  const [visualDraft, setVisualDraft] = useState<VisualAnnotationDraft | null>(null);
  const [draftSelection, setDraftSelection] = useState<TextSelectionEvent | null>(null);
  const [visualSaving, setVisualSaving] = useState(false);
  const [visualSaveError, setVisualSaveError] = useState<string | null>(null);
  const [visualAnnotations, setVisualAnnotations] = useState<Map<string, VisualAnnotation>>(
    () => new Map(),
  );
  const [visualFilters, setVisualFilters] = useState<VisualAnnotationFilters>({
    scope: "page",
    status: "active",
    kind: "all",
  });
  const [visualListIds, setVisualListIds] = useState<string[]>([]);
  const [visualListPage, setVisualListPage] = useState(1);
  const [visualListPages, setVisualListPages] = useState(0);
  const [visualListLoading, setVisualListLoading] = useState(false);
  const [visualReloadKey, setVisualReloadKey] = useState(0);
  const [selectedAnnotationId, setSelectedAnnotationId] = useState<string | null>(null);
  const [recentVisualAnnotationId, setRecentVisualAnnotationId] = useState<string | null>(null);
  const [recentConceptEvidence, setRecentConceptEvidence] = useState<ConceptEvidence | null>(null);
  const [reviewOpen, setReviewOpen] = useState(false);
  const [reviewMode, setReviewMode] = useState<"marks" | "knowledge">("marks");
  const [quickNoteOpen, setQuickNoteOpen] = useState(false);
  const [quickNoteBody, setQuickNoteBody] = useState("");
  const [conceptGroups, setConceptGroups] = useState<DocumentConceptGroup[]>([]);
  const [unlinkedVisualAnnotations, setUnlinkedVisualAnnotations] = useState<UnlinkedVisualAnnotation[]>([]);
  const [conceptLoading, setConceptLoading] = useState(false);
  const [conceptListPage, setConceptListPage] = useState(1);
  const [conceptListPages, setConceptListPages] = useState(0);
  const [conceptReloadKey, setConceptReloadKey] = useState(0);
  const [saveStatus, setSaveStatus] = useState<SaveStatus>("idle");
  const [pageRenderFailure, setPageRenderFailure] = useState<number | null>(null);

  const containerRef = useRef<HTMLDivElement>(null);
  const stageRef = useRef<HTMLElement>(null);
  const viewerRef = useRef<HTMLDivElement>(null);
  const thumbnailsRef = useRef<HTMLDivElement>(null);
  const controllerRef = useRef<PdfReaderController | null>(null);
  const currentPageRef = useRef(1);
  const totalPagesRef = useRef(0);
  const selectionRef = useRef<TextSelectionEvent | null>(null);
  const visualAnnotationsRef = useRef<Map<string, VisualAnnotation>>(new Map());
  visualAnnotationsRef.current = visualAnnotations;
  const zoomModeRef = useRef<ZoomChangedEventV1["mode"]>("fit_width");
  const onEventRef = useRef(onEvent);
  onEventRef.current = onEvent;
  const emitEvent = useCallback(
    (event: AdvancedReaderEventV1) => emitLocalEvent(onEventRef.current, event),
    [],
  );
  const mergeVisualAnnotations = useCallback((items: readonly VisualAnnotation[]) => {
    setVisualAnnotations((current) => mergeVisualAnnotationSnapshots(current, items));
  }, []);

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
    setVisualDraft(null);
    setDraftSelection(null);
    setVisualSaving(false);
    setVisualSaveError(null);
    setVisualAnnotations(new Map());
    setVisualListIds([]);
    setVisualListPage(1);
    setVisualListPages(0);
    setVisualReloadKey(0);
    setSelectedAnnotationId(null);
    setRecentVisualAnnotationId(null);
    setRecentConceptEvidence(null);
    setReviewOpen(false);
    setReviewMode("marks");
    setQuickNoteOpen(false);
    setQuickNoteBody("");
    setConceptGroups([]);
    setUnlinkedVisualAnnotations([]);
    setConceptListPage(1);
    setConceptListPages(0);
    setConceptReloadKey(0);
    setSearchQuery("");
    setSearchStatus("idle");
    setSearchCurrent(0);
    setSearchTotal(0);
    setPageRenderFailure(null);
    currentPageRef.current = 1;
    api.getMetadata(documentId, abortController.signal)
      .then((value) => {
        if (!abortController.signal.aborted) {
          setMetadata(value);
          const initialPage = value.reading_state.current_page ?? 1;
          currentPageRef.current = initialPage;
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
    const renderedPages = new Set<number>();
    const failedPages = new Set<number>();
    let pageRenderFailureEmitted = false;

    const showCurrentPageRenderFailure = () => {
      setPhase("page_render_failed");
      if (!pageRenderFailureEmitted) {
        pageRenderFailureEmitted = true;
        emitEvent({
          schema_version: 1,
          event_type: "document_load_failed",
          document_id: metadata.document_id,
          version_id: metadata.version.version_id,
          error_code: "page_render_failed",
        });
      }
    };

    const clearSelectionEvent = (reason: SelectionClearReason) => {
      const hadSelection = selectionRef.current !== null;
      selectionRef.current = null;
      setSelection(null);
      setSelectionPageLabel(null);
      setVisualDraft(null);
      setDraftSelection(null);
      setVisualSaveError(null);
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
      setRecentVisualAnnotationId(null);
      setRecentConceptEvidence(null);
      setSelectedAnnotationId(null);
      setReviewOpen(false);
      setQuickNoteOpen(false);
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
          totalPagesRef.current = safePages;
          setTotalPages(safePages);
          emitEvent({
            schema_version: 1,
            event_type: "document_loaded",
            document_id: metadata.document_id,
            version_id: metadata.version.version_id,
            total_pages: safePages,
            initial_pdf_page: safePdfPage(metadata.reading_state.current_page, safePages),
          });
        },
        onPageRendered(pdfPage) {
          renderedPages.add(pdfPage);
          failedPages.delete(pdfPage);
          setPageRenderFailure((current) =>
            current === pdfPage ? (failedPages.values().next().value ?? null) : current,
          );
          if (pdfPage === currentPageRef.current) setPhase("ready");
        },
        onPageRenderFailed(pdfPage) {
          failedPages.add(pdfPage);
          setPageRenderFailure(pdfPage);
          if (pdfPage === currentPageRef.current) showCurrentPageRenderFailure();
        },
        onPageChanged(pdfPage, origin) {
          clearSelectionEvent("page_change");
          const pages = safeTotalPageCount(totalPagesRef.current);
          const safePage = safePdfPage(pdfPage, pages);
          currentPageRef.current = safePage;
          setCurrentPage(safePage);
          if (failedPages.has(safePage)) showCurrentPageRenderFailure();
          else if (renderedPages.has(safePage)) setPhase("ready");
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
    controller.setVisualAnnotations(
      [...visualAnnotationsRef.current.values()].map(renderVisualAnnotation),
    );

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

  useEffect(() => {
    controllerRef.current?.setVisualAnnotations(
      [...visualAnnotations.values()].map(renderVisualAnnotation),
    );
  }, [visualAnnotations]);

  useEffect(() => {
    setVisualListPage(1);
    setVisualListIds([]);
  }, [currentPage, visualFilters.scope, visualFilters.status]);

  useEffect(() => {
    if (metadata === null) return;
    const abortController = new AbortController();
    setVisualListLoading(true);
    void api.listVisualAnnotations(
      metadata.document_id,
      {
        pdfPage: visualFilters.scope === "page" ? currentPage : undefined,
        status: visualFilters.status,
        page: visualListPage,
        limit: visualFilters.scope === "page" ? 100 : 25,
      },
      abortController.signal,
    ).then((result) => {
      if (abortController.signal.aborted) return;
      mergeVisualAnnotations(result.items);
      const ids = result.items.map((item) => item.annotation_id);
      setVisualListIds((current) => visualListPage === 1
        ? ids
        : [...new Set([...current, ...ids])]);
      setVisualListPages(result.pages);
    }).catch(() => undefined).finally(() => {
      if (!abortController.signal.aborted) setVisualListLoading(false);
    });
    return () => abortController.abort();
  }, [
    api,
    currentPage,
    mergeVisualAnnotations,
    metadata,
    visualFilters.scope,
    visualFilters.status,
    visualListPage,
    visualReloadKey,
  ]);

  useEffect(() => {
    if (metadata === null) return;
    const abortController = new AbortController();
    const pages = [currentPage - 1, currentPage, currentPage + 1].filter(
      (page) => page >= 1 && (totalPages <= 0 || page <= totalPages),
    );
    void Promise.all(pages.map((pdfPage) => api.listVisualAnnotations(
      metadata.document_id,
      { pdfPage, status: "active", page: 1, limit: 100 },
      abortController.signal,
    ))).then((results) => {
      if (!abortController.signal.aborted) {
        mergeVisualAnnotations(results.flatMap((result) => result.items));
      }
    }).catch(() => undefined);
    return () => abortController.abort();
  }, [api, currentPage, mergeVisualAnnotations, metadata, totalPages, visualReloadKey]);

  useEffect(() => {
    if (metadata === null || !metadata.capabilities.concept_search) return;
    const abortController = new AbortController();
    setConceptLoading(true);
    void Promise.all([
      api.listDocumentConceptEvidence(
        metadata.document_id,
        { status: "all", page: conceptListPage, limit: 50 },
        abortController.signal,
      ),
      api.listUnlinkedVisualAnnotations(
        metadata.document_id,
        { pdfPage: currentPage, page: 1, limit: 50 },
        abortController.signal,
      ),
    ]).then(([concepts, unlinked]) => {
      if (abortController.signal.aborted) return;
      setConceptGroups((current) => conceptListPage === 1
        ? concepts.items
        : [...current, ...concepts.items]);
      setConceptListPages(concepts.pages);
      setUnlinkedVisualAnnotations(unlinked.items);
    }).catch(() => undefined).finally(() => {
      if (!abortController.signal.aborted) setConceptLoading(false);
    });
    return () => abortController.abort();
  }, [api, conceptListPage, conceptReloadKey, currentPage, metadata]);

  const ready = phase === "ready" || phase === "page_render_failed";
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

  const beginVisualAnnotation = (kind: VisualAnnotationKind) => {
    if (!visualWriteEnabled(metadata) || !isPersistableSelection(selection)) return;
    const annotationId = newVisualAnnotationId();
    if (annotationId === null) {
      setVisualSaveError("Este navegador no ofrece un generador seguro de identidad.");
      return;
    }
    setDraftSelection(selection);
    setVisualDraft({
      annotationId,
      kind,
      color: "yellow",
      body: "",
      tagsText: "",
    });
    setVisualSaveError(null);
    setRecentConceptEvidence(null);
    setReviewOpen(false);
    setQuickNoteOpen(false);
  };

  const cancelVisualDraft = () => {
    if (visualSaving) return;
    setVisualDraft(null);
    setDraftSelection(null);
    setVisualSaveError(null);
  };

  const saveVisualAnnotation = async () => {
    if (
      metadata === null ||
      visualDraft === null ||
      !isPersistableSelection(draftSelection) ||
      visualSaving
    ) return;
    const pdfPage = draftSelection.pdf_page;
    const canonicalRects = controllerRef.current?.canonicalizeSelection(
      pdfPage,
      draftSelection.rects_normalized,
    ) ?? null;
    if (canonicalRects === null || canonicalRects.length === 0) {
      setVisualSaveError("No se pudo convertir la selección a geometría canónica.");
      return;
    }
    const payload: CreateVisualAnnotation = {
      annotation_id: visualDraft.annotationId,
      version_id: metadata.version.version_id,
      document_sha256: metadata.version.sha256,
      pdf_page: pdfPage,
      kind: visualDraft.kind,
      quote_text: draftSelection.selected_text,
      rects: canonicalRects,
      capture_rotation: draftSelection.rotation,
      color_label: visualDraft.color,
      body: visualDraft.body,
      tags: parseVisualAnnotationTags(visualDraft.tagsText),
    };
    setVisualSaving(true);
    setVisualSaveError(null);
    try {
      const annotation = await api.createVisualAnnotation(metadata.document_id, payload);
      mergeVisualAnnotations([annotation]);
      setVisualReloadKey((value) => value + 1);
      setRecentVisualAnnotationId(annotation.annotation_id);
      setRecentConceptEvidence(null);
      setVisualDraft(null);
      setDraftSelection(null);
      controllerRef.current?.clearSelection("user");
    } catch (reason) {
      const message = reason instanceof ReaderApiError && reason.code === "visual_annotations_not_ready"
        ? "Inicializa Notes & Evidence en Maintenance para guardar marcas visuales."
        : "No se pudo guardar la marca visual. Puedes reintentar sin duplicarla.";
      setVisualSaveError(message);
    } finally {
      setVisualSaving(false);
    }
  };

  const updateVisualAnnotation = async (
    annotationId: string,
    patch: UpdateVisualAnnotation,
  ) => {
    const annotation = await api.updateVisualAnnotation(annotationId, patch);
    mergeVisualAnnotations([annotation]);
    setVisualReloadKey((value) => value + 1);
  };

  const archiveVisualAnnotation = async (annotationId: string) => {
    const annotation = await api.archiveVisualAnnotation(annotationId);
    mergeVisualAnnotations([annotation]);
    setVisualReloadKey((value) => value + 1);
  };

  const reactivateVisualAnnotation = async (annotationId: string) => {
    const annotation = await api.reactivateVisualAnnotation(annotationId);
    mergeVisualAnnotations([annotation]);
    setVisualReloadKey((value) => value + 1);
  };

  const navigateToVisualAnnotation = (annotation: VisualAnnotation) => {
    if (annotation.visual_status === "exact" && annotation.status === "active") {
      controllerRef.current?.focusVisualAnnotation(annotation.annotation_id);
    } else {
      controllerRef.current?.goToPage(annotation.pdf_page, "pdfjs");
    }
  };

  const openConceptWizard = async (annotationId: string) => {
    const known = visualAnnotationsRef.current.get(annotationId);
    if (known !== undefined) {
      setSelectedAnnotationId(annotationId);
      return;
    }
    try {
      const annotation = await api.getVisualAnnotation(annotationId);
      mergeVisualAnnotations([annotation]);
      setSelectedAnnotationId(annotation.annotation_id);
    } catch {
      // The bounded read panels will refresh; arbitrary server text is never exposed.
    }
  };

  const refreshConceptEvidence = () => {
    setConceptListPage(1);
    setConceptReloadKey((value) => value + 1);
  };

  const archiveConceptEvidence = async (evidenceLinkId: string) => {
    await api.archiveConceptEvidence(evidenceLinkId);
    refreshConceptEvidence();
  };

  const reactivateConceptEvidence = async (evidenceLinkId: string) => {
    await api.reactivateConceptEvidence(evidenceLinkId);
    refreshConceptEvidence();
  };

  const navigateToConceptEvidence = (evidence: ConceptEvidence) => {
    const context = evidence.annotation;
    if (context === null) return;
    controllerRef.current?.goToPage(context.pdf_page, "pdfjs");
    window.setTimeout(() => {
      controllerRef.current?.focusVisualAnnotation(context.annotation_id);
    }, 0);
  };

  const sidebarVisualAnnotations = visualListIds
    .map((annotationId) => visualAnnotations.get(annotationId))
    .filter((annotation): annotation is VisualAnnotation => annotation !== undefined);
  const canPersistVisualAnnotations = visualWriteEnabled(metadata);
  const selectedConceptAnnotation = selectedAnnotationId === null
    ? null
    : visualAnnotations.get(selectedAnnotationId) ?? null;
  const conceptEvidenceByAnnotation = conceptGroups
    .flatMap((group) => group.evidence)
    .reduce<Record<string, ConceptEvidence[]>>((result, evidence) => {
      const annotationId = evidence.annotation?.annotation_id;
      if (annotationId !== undefined) {
        (result[annotationId] ??= []).push(evidence);
      }
      return result;
    }, {});
  const recentVisualAnnotation = recentVisualAnnotationId === null
    ? null
    : visualAnnotations.get(recentVisualAnnotationId) ?? null;
  const activePageMarks = [...visualAnnotations.values()].filter(
    (annotation) => annotation.status === "active" && annotation.pdf_page === currentPage,
  );
  const pageConceptCount = conceptGroups.reduce((count, group) => count + (
    group.evidence.some((item) => item.annotation?.pdf_page === currentPage) ? 1 : 0
  ), 0);

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

        <main ref={stageRef} className="pdf-stage" aria-label="Documento PDF">
          {phase === "loading_pdf" && (
            <div className="pdf-loading" role="status">Renderizando PDF con PDF.js…</div>
          )}
          {pageRenderFailure !== null && (
            <div
              className="pdf-render-failure"
              role="alert"
              data-error-code="page_render_failed"
            >
              <strong>No se pudo renderizar PDF page {pageRenderFailure}.</strong>
              <span>El lector no ocultará una página en blanco.</span>
              <button
                type="button"
                onClick={() => {
                  if (phase === "page_render_failed") setPhase("loading_pdf");
                  controllerRef.current?.retryPage(pageRenderFailure);
                }}
              >
                Reintentar página
              </button>
            </div>
          )}
          <SelectionActionToolbar
            selection={selection}
            enabled={canPersistVisualAnnotations && visualDraft === null}
            stageRef={stageRef}
            viewerRef={viewerRef}
            onChoose={beginVisualAnnotation}
            onCancel={() => controllerRef.current?.clearSelection("user")}
          />
          <div ref={containerRef} id="viewerContainer" tabIndex={0}>
            <div ref={viewerRef} id="viewer" className="pdfViewer" />
          </div>
        </main>

        <aside className="reader-inspector" aria-label="Inspector" aria-hidden={!inspectorOpen}>
          {selectedConceptAnnotation !== null ? (
            <ConceptLinkWizard
              api={api}
              metadata={metadata}
              annotation={selectedConceptAnnotation}
              canWrite={metadata.capabilities.concept_linking}
              onSaved={(evidence) => {
                setRecentConceptEvidence(evidence);
                setSelectedAnnotationId(null);
                setRecentVisualAnnotationId(null);
                refreshConceptEvidence();
              }}
              onCancel={() => setSelectedAnnotationId(null)}
            />
          ) : recentConceptEvidence !== null ? (
            <section className="inspector-card success-card" role="status">
              <div className="eyebrow">Concepto asociado ✓</div>
              <h2>{recentConceptEvidence.concept.title}</h2>
              <p>{recentConceptEvidence.link_type_label}</p>
              {recentConceptEvidence.annotation !== null && (
                <>
                  <blockquote className="selection-text">
                    {recentConceptEvidence.annotation.quote_text}
                  </blockquote>
                  <p className="visual-page-label">PDF page {recentConceptEvidence.annotation.pdf_page}</p>
                </>
              )}
              <button type="button" className="primary-button" onClick={() => setRecentConceptEvidence(null)}>
                Volver a leer
              </button>
            </section>
          ) : recentVisualAnnotation !== null ? (
            <section className="inspector-card saved-visual-action" role="status">
              <div className="eyebrow">
                {recentVisualAnnotation.kind === "highlight" ? "Highlight guardado ✓" : "Underline guardado ✓"}
              </div>
              <blockquote className="selection-text">{recentVisualAnnotation.quote_text}</blockquote>
              <p className="visual-page-label">PDF page {recentVisualAnnotation.pdf_page}</p>
              <div className="button-row">
                <button type="button" onClick={() => void openConceptWizard(recentVisualAnnotation.annotation_id)}>
                  Asociar concepto
                </button>
                <button type="button" onClick={() => {
                  setRecentVisualAnnotationId(null);
                  setQuickNoteOpen(true);
                }}>Añadir nota</button>
                <button type="button" onClick={() => setRecentVisualAnnotationId(null)}>Seguir leyendo</button>
              </div>
            </section>
          ) : visualDraft !== null && draftSelection !== null ? (
            <VisualAnnotationConfirmation
              draft={visualDraft}
              selection={draftSelection}
              pageLabel={selectionPageLabel}
              saving={visualSaving}
              error={visualSaveError}
              onChange={setVisualDraft}
              onSave={() => void saveVisualAnnotation()}
              onCancel={cancelVisualDraft}
            />
          ) : selection !== null ? (
            <SelectionInspector
              selection={selection}
              pageLabel={selectionPageLabel}
              persistenceEnabled={canPersistVisualAnnotations}
              onChoose={beginVisualAnnotation}
              onClear={() => controllerRef.current?.clearSelection("user")}
            />
          ) : quickNoteOpen ? (
            <section className="inspector-card quick-note" aria-labelledby="quick-note-heading">
              <div className="eyebrow">Nota rápida</div>
              <h2 id="quick-note-heading">Añadir nota</h2>
              <label>
                Cuerpo de la nota
                <textarea
                  aria-label="Cuerpo de la nota"
                  rows={6}
                  value={quickNoteBody}
                  onChange={(event) => setQuickNoteBody(event.target.value)}
                />
              </label>
              <p className="warning-banner">Guarda notas desde Leer en Reading Space.</p>
              <div className="button-row">
                <button type="button" className="primary-button" disabled>Guardar</button>
                <button type="button" onClick={() => { setQuickNoteOpen(false); setQuickNoteBody(""); }}>
                  Cancelar
                </button>
              </div>
            </section>
          ) : reviewOpen && reviewMode === "marks" ? (
            <div className="contextual-review">
              <nav className="review-switcher" aria-label="Revisión del lector">
                <button type="button" aria-current="page">Marcas</button>
                <button type="button" onClick={() => setReviewMode("knowledge")}>Conocimiento</button>
                <button type="button" onClick={() => setReviewOpen(false)}>Volver a leer</button>
              </nav>
              <VisualAnnotationsPanel
                annotations={sidebarVisualAnnotations}
                currentPage={currentPage}
                filters={visualFilters}
                loading={visualListLoading}
                hasMore={visualListPage < visualListPages}
                canMutate={canPersistVisualAnnotations}
                canLinkConcepts={metadata.capabilities.concept_linking}
                canArchiveConceptLinks={metadata.capabilities.concept_link_archive}
                canReactivateConceptLinks={metadata.capabilities.concept_link_reactivate}
                conceptEvidenceByAnnotation={conceptEvidenceByAnnotation}
                onFilters={setVisualFilters}
                onLoadMore={() => setVisualListPage((value) => value + 1)}
                onNavigate={navigateToVisualAnnotation}
                onUpdate={updateVisualAnnotation}
                onArchive={archiveVisualAnnotation}
                onReactivate={reactivateVisualAnnotation}
                onLinkConcept={(annotation) => setSelectedAnnotationId(annotation.annotation_id)}
                onArchiveConceptLink={archiveConceptEvidence}
                onReactivateConceptLink={reactivateConceptEvidence}
              />
            </div>
          ) : reviewOpen && metadata.capabilities.concept_search ? (
            <div className="contextual-review">
              <nav className="review-switcher" aria-label="Revisión del lector">
                <button type="button" onClick={() => setReviewMode("marks")}>Marcas</button>
                <button type="button" aria-current="page">Conocimiento</button>
                <button type="button" onClick={() => setReviewOpen(false)}>Volver a leer</button>
              </nav>
              <ConceptPanels
              groups={conceptGroups}
              unlinked={unlinkedVisualAnnotations}
              currentPage={currentPage}
              loading={conceptLoading}
              canLink={metadata.capabilities.concept_linking}
              canArchive={metadata.capabilities.concept_link_archive}
              canReactivate={metadata.capabilities.concept_link_reactivate}
              hasMore={conceptListPage < conceptListPages}
              onLoadMore={() => setConceptListPage((value) => value + 1)}
              onLink={(annotationId) => void openConceptWizard(annotationId)}
              onNavigate={navigateToConceptEvidence}
              onArchive={archiveConceptEvidence}
              onReactivate={reactivateConceptEvidence}
              />
            </div>
          ) : (
            <section className="inspector-card reading-context" aria-labelledby="reading-context-heading">
              <div className="eyebrow">Lectura</div>
              <h2 id="reading-context-heading">{pageLabel.display_label}</h2>
              <p>{activePageMarks.length} marcas · {pageConceptCount} conceptos</p>
              <div className="button-row">
                <button type="button" className="primary-button" onClick={() => setQuickNoteOpen(true)}>
                  Nota rápida
                </button>
                <button type="button" onClick={() => { setReviewMode("marks"); setReviewOpen(true); }}>
                  Revisar marcas
                </button>
              </div>
              {saveStatus === "saved" && <p className="save-feedback success" role="status">Posición guardada.</p>}
              {saveStatus === "error" && <p className="save-feedback error" role="alert">No se pudo guardar la posición.</p>}
            </section>
          )}
        </aside>
      </div>
    </div>
  );
}
