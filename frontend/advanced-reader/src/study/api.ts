/** Activity API: opaque library scope, canonical operations, no MongoDB credentials. */
import type {
  Data,
  Intent,
  Node,
  ReadingNote,
  Result,
  SourceDocument,
} from "../knowledge-map/model";

export type StudyContext = {
  library_id: string;
  runtime_id: string;
  name: string;
  preparation: {
    state: "ready" | "pending" | "incompatible" | "unverified";
    reason: string;
    version: string;
    notes_ready: boolean;
    reading_ready: boolean;
  };
};
export type Bibliography = {
  title?: string;
  year?: number;
  doi?: string;
  isbn?: string[];
  authors?: { literal?: string; family?: string; given?: string }[];
};
export type SourceSummary = {
  source_id: string;
  name: string;
  description?: string;
  bibliography?: Bibliography[];
};
export type SourceDetail = SourceSummary & {
  documents: SourceDocument[];
  references: Bibliography[];
};
export type Page<T> = { items: T[]; total: number; page: number };
export type NoteDetail = ReadingNote & { reference_id: string | null };
export type ConceptDetail = Node & {
  source_id: string;
  passages: {
    document_id: string;
    pdf_page: number | null;
    quote: string;
    annotation_id: string | null;
  }[];
};

export class StudyApiError extends Error {
  constructor(
    message: string,
    readonly code = "unavailable",
  ) {
    super(message);
  }
}
export async function studyRequest<T>(
  path: string,
  context?: StudyContext,
  body?: unknown,
  signal?: AbortSignal,
): Promise<T> {
  if (!path.startsWith("/") || path.startsWith("//"))
    throw new StudyApiError("Ruta de biblioteca no válida.");
  let response: Response;
  try {
    response = await fetch("/api/study/v1" + path, {
      method: body === undefined ? "GET" : "POST",
      signal,
      credentials: "same-origin",
      redirect: "error",
      cache: "no-store",
      headers: {
        Accept: "application/json",
        ...(context ? { "X-MathMongo-Library": context.library_id } : {}),
        ...(body === undefined ? {} : { "Content-Type": "application/json" }),
      },
      ...(body === undefined ? {} : { body: JSON.stringify(body) }),
    });
  } catch (reason) {
    if (signal?.aborted) throw reason;
    throw new StudyApiError(
      "No se confirmó la conexión. El borrador se conserva; reintenta el mismo envío.",
    );
  }
  const value = await response.json();
  if (!response.ok)
    throw new StudyApiError(
      value.error?.message ??
        "No se pudo completar la operación. Conserva el borrador.",
      value.error?.code,
    );
  return value as T;
}
export const executeStudy = (context: StudyContext, intent: Intent) =>
  studyRequest<Result>("/operations", context, intent);
export const getOverview = (context: StudyContext, signal?: AbortSignal) =>
  studyRequest<Data>("/overview", context, undefined, signal);
export function bibliographyLabel(item?: Bibliography): string {
  if (!item) return "";
  const authors = item.authors
    ?.map((a) => a.literal || [a.given, a.family].filter(Boolean).join(" "))
    .join(", ");
  return [authors, item.year].filter(Boolean).join(" · ");
}
