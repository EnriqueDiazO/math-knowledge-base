export interface AdvancedReaderEventEnvelopeV1 {
  schema_version: 1;
  event_type: AdvancedReaderEventV1["event_type"];
  document_id: string;
  version_id: string | null;
}

export type PublicReaderErrorCode =
  | "invalid_document_id"
  | "document_not_found"
  | "document_archived"
  | "document_not_pdf"
  | "integrity_error"
  | "blob_missing"
  | "invalid_range"
  | "multiple_ranges_not_supported"
  | "page_invalid"
  | "database_unavailable"
  | "frontend_not_built"
  | "internal_error"
  | "api_unavailable"
  | "pdfjs_load_error"
  | "unsupported_document";

export type PageChangeOrigin =
  | "initial"
  | "toolbar"
  | "page_input"
  | "thumbnail"
  | "keyboard"
  | "pdfjs";

export type SelectionClearReason =
  | "user"
  | "empty"
  | "page_change"
  | "rotation_change"
  | "document_change"
  | "version_change"
  | "load_failure"
  | "unmount";

export interface NormalizedRect {
  x: number;
  y: number;
  width: number;
  height: number;
}

export type SelectionGeometryStatus = "valid" | "cross_page" | "unresolved";

export interface DocumentLoadedEventV1 {
  schema_version: 1;
  event_type: "document_loaded";
  document_id: string;
  version_id: string;
  total_pages: number;
  initial_pdf_page: number;
}

export interface DocumentLoadFailedEventV1 {
  schema_version: 1;
  event_type: "document_load_failed";
  document_id: string;
  version_id: string | null;
  error_code: PublicReaderErrorCode;
}

export interface PageChangedEventV1 {
  schema_version: 1;
  event_type: "page_changed";
  document_id: string;
  version_id: string;
  pdf_page: number;
  total_pages: number;
  book_page_label: string | null;
  origin: PageChangeOrigin;
}

export interface ZoomChangedEventV1 {
  schema_version: 1;
  event_type: "zoom_changed";
  document_id: string;
  version_id: string;
  scale: number;
  mode: "custom" | "actual_size" | "fit_width" | "fit_page";
}

export interface RotationChangedEventV1 {
  schema_version: 1;
  event_type: "rotation_changed";
  document_id: string;
  version_id: string;
  rotation: 0 | 90 | 180 | 270;
  direction: "clockwise" | "counterclockwise";
}

export interface SearchStartedEventV1 {
  schema_version: 1;
  event_type: "search_started";
  document_id: string;
  version_id: string;
  query: string;
  case_sensitive: boolean;
  whole_words: boolean;
  direction: "next" | "previous";
}

export interface SearchResultEventV1 {
  schema_version: 1;
  event_type: "search_result";
  document_id: string;
  version_id: string;
  status: "searching" | "found" | "not_found" | "cancelled";
  current_match: number | null;
  total_matches: number | null;
}

export interface TextSelectionEventV1 {
  schema_version: 1;
  event_type: "text_selection";
  document_id: string;
  version_id: string;
  pdf_page: number | null;
  selected_text: string;
  rects_normalized: NormalizedRect[];
  rotation: 0 | 90 | 180 | 270;
  scale: number;
  cross_page: boolean;
  geometry_status: SelectionGeometryStatus;
}

export interface SelectionClearedEventV1 {
  schema_version: 1;
  event_type: "selection_cleared";
  document_id: string;
  version_id: string;
  reason: SelectionClearReason;
}

export type ReadingStatus = "unread" | "in_progress" | "completed" | "deferred";

export interface ReadingPositionSavedEventV1 {
  schema_version: 1;
  event_type: "reading_position_saved";
  document_id: string;
  version_id: string;
  pdf_page: number;
  reading_status: ReadingStatus;
}

export type AdvancedReaderEventV1 =
  | DocumentLoadedEventV1
  | DocumentLoadFailedEventV1
  | PageChangedEventV1
  | ZoomChangedEventV1
  | RotationChangedEventV1
  | SearchStartedEventV1
  | SearchResultEventV1
  | TextSelectionEventV1
  | SelectionClearedEventV1
  | ReadingPositionSavedEventV1;

export type TextSelectionEvent = TextSelectionEventV1;
