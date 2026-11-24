/** Never combine local content/citation with another writer's optimistic revision. */
import { emptyLocator } from "../knowledge-map/bibliography";
import type { Intent } from "../knowledge-map/model";
import type { NoteDetail } from "./api";
export function noteMatchesIntent(
  note: NoteDetail,
  sent: Intent,
  acknowledgedId: string,
): boolean {
  if (
    note.note_id !== acknowledgedId ||
    (!!sent.note_id && note.note_id !== sent.note_id)
  )
    return false;
  if (
    note.body !== sent.contenido_latex ||
    note.title !== sent.titulo?.trim() ||
    note.source_id !== sent.source_id
  )
    return false;
  if ((note.document_id || "") !== (sent.document_id || "")) return false;
  if ((note.reference_id || "") !== (sent.reference_id || "")) return false;
  if (sent.reference_id) {
    const expected = { ...emptyLocator(), ...sent.reference_locator },
      actual = { ...emptyLocator(), ...note.reference_locator };
    return (Object.keys(expected) as (keyof typeof expected)[]).every(
      (key) => expected[key] === actual[key],
    );
  }
  return true;
}
