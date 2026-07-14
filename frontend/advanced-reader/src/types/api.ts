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
  | "visual_annotation_editing"
  | "visual_annotation_archiving"
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

export type VisualAnnotationKind = "highlight" | "underline";
export type VisualAnnotationStatus = "active" | "archived";
export type VisualAnnotationColor = "yellow" | "green" | "blue" | "pink" | "purple";
export type VisualAnnotationCompatibility =
  | "exact"
  | "version_mismatch"
  | "invalid_geometry"
  | "logical_only";

export interface CanonicalVisualRect {
  x: number;
  y: number;
  width: number;
  height: number;
}

export interface VisualAnnotationAnchor {
  version_id: string;
  document_sha256: string;
  coordinate_space: "normalized_unrotated_crop_box";
  capture_rotation: 0 | 90 | 180 | 270;
  rects: CanonicalVisualRect[];
}

export interface VisualAnnotation {
  annotation_id: string;
  document_id: string;
  kind: VisualAnnotationKind;
  status: VisualAnnotationStatus;
  pdf_page: number;
  page_label: string | null;
  quote_text: string;
  body: string;
  color_label: string | null;
  tags: string[];
  visual_status: VisualAnnotationCompatibility;
  visual_anchor: VisualAnnotationAnchor;
  created_at: string;
  updated_at: string;
  archived_at: string | null;
}

export interface VisualAnnotationList {
  items: VisualAnnotation[];
  page: number;
  page_size: number;
  total: number;
  pages: number;
}

export interface CreateVisualAnnotation {
  annotation_id: string;
  version_id: string;
  document_sha256: string;
  pdf_page: number;
  kind: VisualAnnotationKind;
  quote_text: string;
  rects: CanonicalVisualRect[];
  capture_rotation: 0 | 90 | 180 | 270;
  color_label: VisualAnnotationColor;
  body: string;
  tags: string[];
}

export interface UpdateVisualAnnotation {
  kind?: VisualAnnotationKind;
  color_label?: VisualAnnotationColor;
  body?: string;
  tags?: string[];
}
