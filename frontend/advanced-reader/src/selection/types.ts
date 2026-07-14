export type { NormalizedRect, TextSelectionEvent } from "../types/events";

export interface SelectionCaptureContext {
  documentId: string;
  versionId: string;
  rotation: number;
  scale: number;
}
