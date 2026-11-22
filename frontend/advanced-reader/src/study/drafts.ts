/** Reuse the existing versioned vault; keep a stable envelope before any write. */
import { DraftVault } from "../knowledge-map/drafts";
import type { Draft, Intent } from "../knowledge-map/model";
import type { CreateVisualAnnotation, DocumentMetadata } from "../types/api";
import type { NoteDetail } from "./api";
export type StudyDraft = Draft & {
  pending?: Intent;
  passage?: CreateVisualAnnotation;
};
export const studyVault = (library: string) =>
  new DraftVault(library, "study-documents");
export function newStudyDraft(
  source: string,
  document?: DocumentMetadata,
  passage?: CreateVisualAnnotation,
): StudyDraft {
  return {
    id: crypto.randomUUID(),
    action: "save_note",
    source,
    title: "",
    content: "",
    type: "nota",
    comment: "",
    categories: "",
    origin: "",
    target: "",
    relation: "requiere_concepto",
    reverse: false,
    revision: "",
    point: [0, 0, 1],
    documentId: document?.document_id,
    referenceId: document?.reference?.reference_id,
    passage,
  };
}
export function noteDraft(note: NoteDetail): StudyDraft {
  return {
    ...newStudyDraft(note.source_id),
    title: note.title,
    content: note.body,
    noteId: note.note_id,
    documentId: note.document_id ?? undefined,
    referenceId: note.reference_id ?? undefined,
    referenceLocator: note.reference_locator ?? undefined,
    revision: note.revision,
  };
}
