export const VISUAL_ANNOTATION_COORDINATE_SPACE =
  "normalized_unrotated_crop_box" as const;

export type VisualAnnotationKind = "highlight" | "underline";
export type VisualAnnotationStatus = "active" | "archived";
export type VisualAnnotationRenderStatus =
  | "exact"
  | "version_mismatch"
  | "invalid_geometry"
  | "logical_only";
export type QuarterTurn = 0 | 90 | 180 | 270;

export interface NormalizedVisualRect {
  x: number;
  y: number;
  width: number;
  height: number;
}

export interface VisualAnnotationRenderAnchor {
  coordinate_space: typeof VISUAL_ANNOTATION_COORDINATE_SPACE;
  capture_rotation: QuarterTurn;
  rects: NormalizedVisualRect[];
}

/**
 * Minimal, transport-independent projection consumed by the PDF overlay.
 * API DTOs may contain additional presentation fields without exposing them to
 * this low-level renderer.
 */
export interface VisualAnnotationRenderItem {
  annotation_id: string;
  kind: VisualAnnotationKind;
  status: VisualAnnotationStatus;
  pdf_page: number;
  color_label: string;
  visual_status: VisualAnnotationRenderStatus;
  visual_anchor: VisualAnnotationRenderAnchor | null;
}

export const VISUAL_COLOR_LABELS = [
  "yellow",
  "green",
  "blue",
  "pink",
  "purple",
] as const;

export type VisualColorLabel = (typeof VISUAL_COLOR_LABELS)[number];
