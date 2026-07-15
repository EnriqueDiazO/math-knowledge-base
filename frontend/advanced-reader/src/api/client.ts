import type {
  ApiErrorBody,
  ConceptEvidenceList,
  ConceptEvidenceWriteResult,
  ConceptSearchResult,
  CreateConceptEvidence,
  CreateVisualAnnotation,
  DocumentConceptSummary,
  DocumentMetadata,
  PageLabel,
  ReadingPageUpdate,
  ReadingStateResponse,
  UpdateVisualAnnotation,
  UnlinkedVisualAnnotationList,
  VisualAnnotation,
  VisualAnnotationList,
} from "../types/api";

const API_ROOT = "/api/advanced-reader";
const DOCUMENT_ID_PATTERN =
  /^doc_[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/;
const ANNOTATION_ID_PATTERN =
  /^ann_[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/;
const EVIDENCE_ID_PATTERN =
  /^ev_[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/;

export class ReaderApiError extends Error {
  readonly code: string;
  readonly status: number;

  constructor(code: string, message: string, status = 0) {
    super(message);
    this.name = "ReaderApiError";
    this.code = code;
    this.status = status;
  }
}

export function isValidDocumentId(value: unknown): value is string {
  return typeof value === "string" && DOCUMENT_ID_PATTERN.test(value);
}

export function documentIdFromSearch(search: string): string | null {
  const parameters = new URLSearchParams(search);
  const documentIds = parameters.getAll("document_id");
  const keys = [...parameters.keys()];
  if (
    documentIds.length !== 1 ||
    keys.length !== 1 ||
    keys[0] !== "document_id" ||
    !isValidDocumentId(documentIds[0])
  ) {
    return null;
  }
  return documentIds[0];
}

function documentPath(documentId: string, suffix = ""): string {
  if (!isValidDocumentId(documentId)) {
    throw new ReaderApiError("invalid_document_id", "El identificador del Document no es válido.");
  }
  return `${API_ROOT}/documents/${encodeURIComponent(documentId)}${suffix}`;
}

function annotationPath(annotationId: string, suffix = ""): string {
  if (!ANNOTATION_ID_PATTERN.test(annotationId)) {
    throw new ReaderApiError("invalid_annotation_id", "La anotación visual no es válida.");
  }
  return `${API_ROOT}/visual-annotations/${encodeURIComponent(annotationId)}${suffix}`;
}

function evidencePath(evidenceLinkId: string, suffix = ""): string {
  if (!EVIDENCE_ID_PATTERN.test(evidenceLinkId)) {
    throw new ReaderApiError("invalid_evidence_id", "El vínculo conceptual no es válido.");
  }
  return `${API_ROOT}/concept-evidence/${encodeURIComponent(evidenceLinkId)}${suffix}`;
}

export function sameOriginUrl(path: string): string {
  if (!path.startsWith(`${API_ROOT}/`) || path.startsWith("//")) {
    throw new ReaderApiError("invalid_api_path", "La ruta de API no está permitida.");
  }
  const url = new URL(path, window.location.origin);
  if (url.origin !== window.location.origin) {
    throw new ReaderApiError("cross_origin_blocked", "La API debe compartir origen con el lector.");
  }
  return `${url.pathname}${url.search}`;
}

async function decodeError(response: Response): Promise<ReaderApiError> {
  let body: ApiErrorBody = {};
  try {
    body = (await response.json()) as ApiErrorBody;
  } catch {
    // The UI intentionally does not expose arbitrary server response text.
  }
  const code = body.error?.code ?? body.code ?? "api_error";
  const message =
    body.error?.message ?? body.message ?? "El lector no pudo completar la solicitud.";
  return new ReaderApiError(code, message, response.status);
}

async function requestJson<T>(path: string, init: RequestInit = {}): Promise<T> {
  let response: Response;
  const headers = new Headers(init.headers);
  if (!headers.has("Accept")) headers.set("Accept", "application/json");
  try {
    response = await fetch(sameOriginUrl(path), {
      ...init,
      cache: "no-store",
      credentials: "same-origin",
      redirect: "error",
      headers,
    });
  } catch {
    throw new ReaderApiError(
      "api_unavailable",
      "No se pudo contactar la API local del lector.",
    );
  }
  if (!response.ok) {
    throw await decodeError(response);
  }
  return (await response.json()) as T;
}

export interface AdvancedReaderApi {
  getMetadata(documentId: string, signal?: AbortSignal): Promise<DocumentMetadata>;
  getPageLabel(documentId: string, pdfPage: number, signal?: AbortSignal): Promise<PageLabel>;
  savePage(
    documentId: string,
    pdfPage: number,
    signal?: AbortSignal,
  ): Promise<ReadingStateResponse>;
  listVisualAnnotations(
    documentId: string,
    options?: {
      pdfPage?: number;
      status?: "active" | "archived" | "all";
      page?: number;
      limit?: number;
    },
    signal?: AbortSignal,
  ): Promise<VisualAnnotationList>;
  createVisualAnnotation(
    documentId: string,
    payload: CreateVisualAnnotation,
    signal?: AbortSignal,
  ): Promise<VisualAnnotation>;
  getVisualAnnotation(annotationId: string, signal?: AbortSignal): Promise<VisualAnnotation>;
  updateVisualAnnotation(
    annotationId: string,
    payload: UpdateVisualAnnotation,
    signal?: AbortSignal,
  ): Promise<VisualAnnotation>;
  archiveVisualAnnotation(annotationId: string, signal?: AbortSignal): Promise<VisualAnnotation>;
  reactivateVisualAnnotation(annotationId: string, signal?: AbortSignal): Promise<VisualAnnotation>;
  searchConcepts(
    query: string,
    options?: { source?: string; conceptType?: string; category?: string; page?: number; limit?: number },
    signal?: AbortSignal,
  ): Promise<ConceptSearchResult>;
  listAnnotationConceptEvidence(
    annotationId: string,
    options?: { status?: "active" | "archived" | "all"; page?: number; limit?: number },
    signal?: AbortSignal,
  ): Promise<ConceptEvidenceList>;
  createAnnotationConceptEvidence(
    annotationId: string,
    payload: CreateConceptEvidence,
    signal?: AbortSignal,
  ): Promise<ConceptEvidenceWriteResult>;
  archiveConceptEvidence(
    evidenceLinkId: string,
    signal?: AbortSignal,
  ): Promise<ConceptEvidenceWriteResult>;
  reactivateConceptEvidence(
    evidenceLinkId: string,
    signal?: AbortSignal,
  ): Promise<ConceptEvidenceWriteResult>;
  listDocumentConceptEvidence(
    documentId: string,
    options?: {
      pdfPage?: number;
      status?: "active" | "archived" | "all";
      page?: number;
      limit?: number;
    },
    signal?: AbortSignal,
  ): Promise<DocumentConceptSummary>;
  listUnlinkedVisualAnnotations(
    documentId: string,
    options?: { pdfPage?: number; page?: number; limit?: number },
    signal?: AbortSignal,
  ): Promise<UnlinkedVisualAnnotationList>;
  pdfUrl(documentId: string): string;
}

const jsonWrite = (body: object, signal?: AbortSignal): RequestInit => ({
  method: "POST",
  signal,
  headers: { Accept: "application/json", "Content-Type": "application/json" },
  body: JSON.stringify(body),
});

export const advancedReaderApi: AdvancedReaderApi = {
  getMetadata(documentId, signal) {
    return requestJson<DocumentMetadata>(documentPath(documentId), { signal });
  },

  getPageLabel(documentId, pdfPage, signal) {
    if (!Number.isInteger(pdfPage) || pdfPage < 1) {
      throw new ReaderApiError("page_invalid", "La página PDF no es válida.");
    }
    const query = new URLSearchParams({ pdf_page: String(pdfPage) });
    return requestJson<PageLabel>(
      documentPath(documentId, `/page-label?${query.toString()}`),
      { signal },
    );
  },

  savePage(documentId, pdfPage, signal) {
    if (!Number.isInteger(pdfPage) || pdfPage < 1) {
      throw new ReaderApiError("page_invalid", "La página PDF no es válida.");
    }
    const payload: ReadingPageUpdate = { pdf_page: pdfPage };
    return requestJson<ReadingStateResponse>(documentPath(documentId, "/reading-state/page"), {
      method: "PUT",
      signal,
      headers: { Accept: "application/json", "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
  },

  listVisualAnnotations(documentId, options = {}, signal) {
    const query = new URLSearchParams();
    if (options.pdfPage !== undefined) {
      if (!Number.isInteger(options.pdfPage) || options.pdfPage < 1) {
        throw new ReaderApiError("page_invalid", "La página PDF no es válida.");
      }
      query.set("pdf_page", String(options.pdfPage));
    }
    query.set("status", options.status ?? "active");
    query.set("page", String(options.page ?? 1));
    query.set("limit", String(options.limit ?? 50));
    return requestJson<VisualAnnotationList>(
      documentPath(documentId, `/visual-annotations?${query.toString()}`),
      { signal },
    );
  },

  createVisualAnnotation(documentId, payload, signal) {
    return requestJson<VisualAnnotation>(
      documentPath(documentId, "/visual-annotations"),
      jsonWrite(payload, signal),
    );
  },

  getVisualAnnotation(annotationId, signal) {
    return requestJson<VisualAnnotation>(annotationPath(annotationId), { signal });
  },

  updateVisualAnnotation(annotationId, payload, signal) {
    return requestJson<VisualAnnotation>(annotationPath(annotationId), {
      ...jsonWrite(payload, signal),
      method: "PATCH",
    });
  },

  archiveVisualAnnotation(annotationId, signal) {
    return requestJson<VisualAnnotation>(
      annotationPath(annotationId, "/archive"),
      jsonWrite({}, signal),
    );
  },

  reactivateVisualAnnotation(annotationId, signal) {
    return requestJson<VisualAnnotation>(
      annotationPath(annotationId, "/reactivate"),
      jsonWrite({}, signal),
    );
  },

  searchConcepts(query, options = {}, signal) {
    const value = query.trim();
    if (!value || Array.from(value).length > 160) {
      throw new ReaderApiError("concept_query_invalid", "La búsqueda debe tener entre 1 y 160 caracteres.");
    }
    const parameters = new URLSearchParams({
      q: value,
      page: String(options.page ?? 1),
      limit: String(options.limit ?? 20),
    });
    if (options.source) parameters.set("source", options.source);
    if (options.conceptType) parameters.set("concept_type", options.conceptType);
    if (options.category) parameters.set("category", options.category);
    return requestJson<ConceptSearchResult>(`${API_ROOT}/concepts/search?${parameters}`, { signal });
  },

  listAnnotationConceptEvidence(annotationId, options = {}, signal) {
    const parameters = new URLSearchParams({
      status: options.status ?? "active",
      page: String(options.page ?? 1),
      limit: String(options.limit ?? 25),
    });
    return requestJson<ConceptEvidenceList>(
      annotationPath(annotationId, `/concept-evidence?${parameters}`),
      { signal },
    );
  },

  createAnnotationConceptEvidence(annotationId, payload, signal) {
    return requestJson<ConceptEvidenceWriteResult>(
      annotationPath(annotationId, "/concept-evidence"),
      jsonWrite(payload, signal),
    );
  },

  archiveConceptEvidence(evidenceLinkId, signal) {
    return requestJson<ConceptEvidenceWriteResult>(
      evidencePath(evidenceLinkId, "/archive"),
      jsonWrite({}, signal),
    );
  },

  reactivateConceptEvidence(evidenceLinkId, signal) {
    return requestJson<ConceptEvidenceWriteResult>(
      evidencePath(evidenceLinkId, "/reactivate"),
      jsonWrite({}, signal),
    );
  },

  listDocumentConceptEvidence(documentId, options = {}, signal) {
    const parameters = new URLSearchParams({
      status: options.status ?? "active",
      page: String(options.page ?? 1),
      limit: String(options.limit ?? 25),
    });
    if (options.pdfPage !== undefined) parameters.set("pdf_page", String(options.pdfPage));
    return requestJson<DocumentConceptSummary>(
      documentPath(documentId, `/visual-concept-evidence?${parameters}`),
      { signal },
    );
  },

  listUnlinkedVisualAnnotations(documentId, options = {}, signal) {
    const parameters = new URLSearchParams({
      page: String(options.page ?? 1),
      limit: String(options.limit ?? 25),
    });
    if (options.pdfPage !== undefined) parameters.set("pdf_page", String(options.pdfPage));
    return requestJson<UnlinkedVisualAnnotationList>(
      documentPath(documentId, `/unlinked-visual-annotations?${parameters}`),
      { signal },
    );
  },

  pdfUrl(documentId) {
    return sameOriginUrl(documentPath(documentId, "/pdf"));
  },
};
