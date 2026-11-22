import { useMemo } from "react";
import ReaderEntry from "../app/ReaderEntry";
import { createAdvancedReaderApi } from "../api/client";
import type { CreateVisualAnnotation, DocumentMetadata } from "../types/api";
import type { StudyContext } from "./api";

export default function ReadingPage({
  context,
  documentId,
  page,
  onCreateNote,
}: {
  context: StudyContext;
  documentId: string;
  page?: number;
  onCreateNote: (
    metadata: DocumentMetadata,
    passage?: CreateVisualAnnotation,
  ) => void;
}) {
  const api = useMemo(
    () => createAdvancedReaderApi(context.library_id),
    [context.library_id],
  );
  return (
    <ReaderEntry
      api={api}
      search={"?document_id=" + encodeURIComponent(documentId) + "&theme=study"}
      initialPdfPage={page}
      onCreateNote={onCreateNote}
    />
  );
}
