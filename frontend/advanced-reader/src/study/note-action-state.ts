/** Revision and response contracts for whole-note operations, independent from rendering. */
export type NoteActionFamily = "diary" | "cornell" | "cpi";
export type NoteActionDescriptor = { title: string; revision: string };
export type NoteActionIntent = {
  action: "duplicate" | "delete";
  request_id: string;
  revision: string;
  title?: string;
};
export type NoteActionState = {
  mode: string;
  reviewTitle: string;
  revision: string;
  typed: string;
  title: string;
  pending: string;
};
export type NoteActionResponse = {
  status?: string;
  note_id: string;
  family?: string;
  revision?: string;
};
export function prepareNoteAction(
  state: NoteActionState,
  note?: NoteActionDescriptor,
): NoteActionIntent | undefined {
  if (!note || state.revision !== note.revision)
    throw new Error(
      "La versión consultada cambió. Vuelve a elegir la operación sobre la nota actual.",
    );
  if (state.mode === "delete") {
    if (state.typed !== state.reviewTitle) return;
    return {
      action: "delete",
      revision: state.revision,
      request_id: crypto.randomUUID(),
    };
  }
  if (state.mode !== "duplicate" || !state.title.trim()) return;
  return {
    action: "duplicate",
    revision: state.revision,
    request_id: crypto.randomUUID(),
    title: state.title,
  };
}
export function confirmedNoteRoute(
  family: NoteActionFamily,
  identity: string,
  intent: NoteActionIntent,
  result: NoteActionResponse,
): string {
  const route =
    family === "diary" ? "/study/notebook" : "/study/notebook/" + family;
  if (intent.action === "delete") {
    if (
      result.status !== "deleted" ||
      result.note_id !== identity ||
      result.family !== family
    )
      throw new Error(
        "No se confirmó la eliminación; conserva esta solicitud y reintenta.",
      );
    return route;
  }
  if (
    result.note_id !== family + "_copy_" + intent.request_id ||
    !result.revision
  )
    throw new Error(
      "No se confirmó la copia; conserva esta solicitud y reintenta.",
    );
  return route + "/" + encodeURIComponent(result.note_id);
}
