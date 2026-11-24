/** A Diario draft stores canonical LaTeX and only submits fields the user changed. */
import type { EditorSnapshot } from "../knowledge-map/document-editor";
export type DiaryFields = {
  title: string;
  latex_body: string;
  date: string;
  project: string;
  context: string;
  tags: string[];
  catalog_reference_ids: string[];
};
export type DiaryDetail = Omit<DiaryFields, "catalog_reference_ids"> & {
  note_id: string;
  revision: string;
  image_count: number;
  references: {
    reference_id: string;
    title: string;
    catalog_reference_id?: string | null;
  }[];
};
export type DiaryDraft = {
  title: string;
  latex_body: string;
  date: string;
  project: string;
  context: string;
  tags: string;
  references: string;
  original: string;
  revision: string;
  snapshot: string;
  pending: string;
  request_id: string;
};
function localDate() {
  const now = new Date();
  return [
    now.getFullYear(),
    String(now.getMonth() + 1).padStart(2, "0"),
    String(now.getDate()).padStart(2, "0"),
  ].join("-");
}
export function diaryFields(draft: DiaryDraft): DiaryFields {
  const references: unknown = JSON.parse(draft.references);
  if (
    !Array.isArray(references) ||
    references.some((item) => typeof item !== "string")
  )
    throw new Error(
      "Asociaciones del borrador dañadas; conserva y descarga el original.",
    );
  return {
    title: draft.title,
    latex_body: draft.latex_body,
    date: draft.date,
    project: draft.project,
    context: draft.context,
    tags: draft.tags.split("\n").filter(Boolean),
    catalog_reference_ids: references,
  };
}
export function diaryDraft(note?: DiaryDetail): DiaryDraft {
  const draft: DiaryDraft = {
    title: note?.title || "",
    latex_body: note?.latex_body || "",
    date: note?.date || (note ? "" : localDate()),
    project: note?.project || "",
    context: note?.context || (note ? "" : "estudio"),
    tags: note?.tags.join("\n") || "",
    references: JSON.stringify(
      note?.references
        .map((item) => item.catalog_reference_id)
        .filter(Boolean) || [],
    ),
    original: "",
    revision: note?.revision || "",
    snapshot: "",
    pending: "",
    request_id: crypto.randomUUID(),
  };
  draft.original = JSON.stringify(diaryFields(draft));
  return draft;
}
export function diaryChanges(draft: DiaryDraft) {
  const original: DiaryFields = JSON.parse(draft.original),
    current = diaryFields(draft);
  if (
    !original ||
    Object.keys(current).some(
      (key) =>
        typeof original[key as keyof DiaryFields] !==
        typeof current[key as keyof DiaryFields],
    )
  )
    throw new Error(
      "La versión original del borrador no es válida; descárgala antes de reiniciar.",
    );
  return Object.fromEntries(
    Object.entries(current).filter(
      ([key, value]) =>
        JSON.stringify(value) !==
        JSON.stringify(original[key as keyof DiaryFields]),
    ),
  );
}
export function diaryRebase(
  draft: DiaryDraft,
  remote: DiaryDetail,
): DiaryDraft {
  const edits = diaryChanges(draft),
    base = diaryDraft(remote),
    values = { ...diaryFields(base), ...edits };
  return {
    ...base,
    ...values,
    tags: values.tags.join("\n"),
    references: JSON.stringify(values.catalog_reference_ids),
    snapshot: "latex_body" in edits ? draft.snapshot : "",
    request_id: draft.request_id,
  };
}
export function diarySnapshot(
  draft: Pick<DiaryDraft, "snapshot">,
): EditorSnapshot | undefined {
  if (!draft.snapshot) return;
  const value: unknown = JSON.parse(draft.snapshot);
  if (!value || typeof value !== "object" || Array.isArray(value))
    throw new Error(
      "La recuperación del editor no es válida; descarga el borrador original.",
    );
  return value as EditorSnapshot;
}
