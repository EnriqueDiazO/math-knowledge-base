export type ReaderCapability =
  | "page_navigation"
  | "thumbnails"
  | "zoom"
  | "rotate"
  | "text_search"
  | "text_selection"
  | "temporary_selection_geometry"
  | "persistent_highlights"
  | "persistent_underlines"
  | "concept_linking";

export type ReaderCapabilities = Record<ReaderCapability, boolean>;

export interface DocumentSourceSummary {
  source_id: string;
  name: string;
}

export interface DocumentReferenceSummary {
  reference_id: string;
  title: string;
}

export interface DocumentVersionSummary {
  version_id: string;
  sha256: string;
  size_bytes: number;
  original_filename: string;
}

export interface ReadingStateSummary {
  status: string;
  current_page: number | null;
  total_pages?: number | null;
  last_opened_at: string | null;
}

export interface PageLabel {
  pdf_page: number;
  book_page_label: string | null;
  display_label: string;
}

export interface DocumentMetadata {
  document_id: string;
  title: string;
  kind: "pdf";
  status: string;
  source: DocumentSourceSummary;
  reference: DocumentReferenceSummary | null;
  version: DocumentVersionSummary;
  reading_state: ReadingStateSummary;
  page_label: PageLabel | null;
  capabilities: ReaderCapabilities;
}

export interface ApiErrorBody {
  code?: string;
  message?: string;
  error?: {
    code?: string;
    message?: string;
  };
}

export interface ReadingPageUpdate {
  pdf_page: number;
}

export interface ReadingStateResponse extends ReadingStateSummary {
  document_id: string;
}
