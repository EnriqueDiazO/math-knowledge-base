import type { TextSelectionEvent } from "../selection/types";
import type { VisualAnnotation, VisualAnnotationColor } from "../types/api";

export type PersistableTextSelection = TextSelectionEvent & {
  pdf_page: number;
  cross_page: false;
  geometry_status: "valid";
};

export const VISUAL_ANNOTATION_COLORS: readonly VisualAnnotationColor[] = [
  "yellow",
  "green",
  "blue",
  "pink",
  "purple",
];

export const VISUAL_QUOTE_PREVIEW_CODE_POINTS = 240;

export function isPersistableSelection(
  selection: TextSelectionEvent | null,
): selection is PersistableTextSelection {
  return selection !== null &&
    selection.geometry_status === "valid" &&
    selection.cross_page === false &&
    selection.pdf_page !== null &&
    selection.rects_normalized.length > 0 &&
    selection.rects_normalized.length <= 64;
}

export function visualAnnotationColor(value: string | null): VisualAnnotationColor {
  return VISUAL_ANNOTATION_COLORS.includes(value as VisualAnnotationColor)
    ? value as VisualAnnotationColor
    : "yellow";
}

export function visualQuotePreview(value: string): string {
  const codePoints = Array.from(value);
  if (codePoints.length <= VISUAL_QUOTE_PREVIEW_CODE_POINTS) return value;
  const content = codePoints
    .slice(0, VISUAL_QUOTE_PREVIEW_CODE_POINTS - 1)
    .join("")
    .trimEnd();
  return `${content}…`;
}

function visualAnnotationRevision(annotation: VisualAnnotation): number {
  const revision = Date.parse(annotation.updated_at);
  return Number.isFinite(revision) ? revision : Number.NEGATIVE_INFINITY;
}

export function mergeVisualAnnotationSnapshots(
  current: ReadonlyMap<string, VisualAnnotation>,
  items: readonly VisualAnnotation[],
): Map<string, VisualAnnotation> {
  const next = new Map(current);
  items.forEach((item) => {
    const existing = next.get(item.annotation_id);
    if (
      existing === undefined ||
      visualAnnotationRevision(item) >= visualAnnotationRevision(existing)
    ) {
      next.set(item.annotation_id, item);
    }
  });
  return next;
}

export function parseVisualAnnotationTags(value: string): string[] {
  const seen = new Set<string>();
  return value.split(",").map((item) => item.replace(/\s+/gu, " ").trim()).filter((item) => {
    const folded = item.toLocaleLowerCase();
    if (!item || seen.has(folded)) return false;
    seen.add(folded);
    return true;
  }).slice(0, 50);
}
