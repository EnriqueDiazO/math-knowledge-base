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
  | "concept_search"
  | "annotation_concept_links"
  | "concept_link_archive"
  | "concept_link_reactivate"
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

export type EvidenceLinkType =
  | "definition_source"
  | "theorem_source"
  | "proof_source"
  | "example_source"
  | "motivation"
  | "citation"
  | "question"
  | "related_context";

export type EvidenceLinkStatus = "active" | "archived";

export interface ConceptSummary {
  concept_legacy_id: string;
  concept_legacy_source: string;
  title: string;
  concept_type: string;
  categories: string[];
  tags: string[];
  evidence_count: number | null;
  evidence_in_document_count: number | null;
  warning: "concept_not_found" | null;
}

export interface ConceptSearchResult {
  items: ConceptSummary[];
  page: number;
  page_size: number;
  has_more: boolean;
}

export interface AnnotationEvidenceContext {
  annotation_id: string;
  kind: VisualAnnotationKind;
  status: VisualAnnotationStatus;
  visual_status: "exact" | "version_mismatch";
  pdf_page: number;
  book_page_label: string | null;
  quote_text: string;
  color_label: string | null;
  annotation_comment: string;
}

export interface ConceptEvidence {
  evidence_link_id: string;
  concept: ConceptSummary;
  link_type: EvidenceLinkType;
  link_type_label: string;
  comment: string | null;
  status: EvidenceLinkStatus;
  created_at: string;
  updated_at: string;
  archived_at: string | null;
  annotation: AnnotationEvidenceContext | null;
}

export interface ConceptEvidenceList {
  items: ConceptEvidence[];
  page: number;
  page_size: number;
  total: number;
  pages: number;
}

export interface CreateConceptEvidence {
  evidence_link_id: string;
  concept_legacy_id: string;
  concept_legacy_source: string;
  link_type: EvidenceLinkType;
  comment: string | null;
}

export interface ConceptEvidenceWriteResult {
  result: "success" | "identical";
  item: ConceptEvidence;
}

export interface DocumentConceptGroup {
  concept: ConceptSummary;
  highlight_count: number;
  underline_count: number;
  pages: number[];
  link_types: EvidenceLinkType[];
  evidence: ConceptEvidence[];
}

export interface DocumentConceptSummary {
  items: DocumentConceptGroup[];
  page: number;
  page_size: number;
  total: number;
  pages: number;
}

export interface UnlinkedVisualAnnotation {
  annotation_id: string;
  kind: VisualAnnotationKind;
  pdf_page: number;
  book_page_label: string | null;
  quote_text: string;
  color_label: string | null;
}

export interface UnlinkedVisualAnnotationList {
  items: UnlinkedVisualAnnotation[];
  page: number;
  page_size: number;
  total: number;
  pages: number;
}
