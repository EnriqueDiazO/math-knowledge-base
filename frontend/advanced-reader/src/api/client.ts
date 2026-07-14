import type {
  ApiErrorBody,
  DocumentMetadata,
  PageLabel,
  ReadingPageUpdate,
  ReadingStateResponse,
} from "../types/api";

const API_ROOT = "/api/advanced-reader";
const DOCUMENT_ID_PATTERN =
  /^doc_[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/;

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
  pdfUrl(documentId: string): string;
}

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

  pdfUrl(documentId) {
    return sameOriginUrl(documentPath(documentId, "/pdf"));
  },
};
