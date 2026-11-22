/** Recoverable room presentation, separate from canonical documents and concepts. */
import type {
  Data,
  Draft,
  RoomState,
  SavedRoom,
  SavedView,
  Intent,
  Result,
} from "./model";
import { freshView, draftFor } from "./model";
import { emptyLocator } from "./bibliography";
import { compareKeys } from "./geometry";
export type Workspace = {
  uid: string;
  revision: string;
  state: RoomState;
  dirty: boolean;
  mode: "general" | "focus" | "compare" | "note";
  focus: string;
  comparison: string[];
  activePane: number;
  selected: string;
  annotation: string;
  noteDraft?: string;
  draftView?: string;
  pending?: Intent;
  result?: Result;
};
export function emptyRoom(): Workspace {
  return {
    uid: crypto.randomUUID(),
    revision: "",
    dirty: false,
    mode: "general",
    focus: "",
    comparison: [],
    activePane: 0,
    selected: "",
    annotation: "",
    state: {
      version: 1,
      name: "Mi habitación de estudio",
      spheres: [],
      document_id: "",
      note_id: "",
      goal_view_uid: "",
      goal_id: "",
    },
  };
}
export function fromSavedRoom(saved: SavedRoom): Workspace {
  return {
    ...emptyRoom(),
    uid: saved.uid,
    revision: saved.revision,
    state: structuredClone(saved.state),
  };
}
export function memberKeys(data: Data, saved: SavedView): Set<string> {
  const explicit = saved.state.members;
  return new Set(
    data.nodes
      .filter((n) => !explicit || explicit.includes(n.key))
      .map((n) => n.key),
  );
}
export function sharedConcepts(
  data: Data,
  first?: SavedView,
  second?: SavedView,
): string[] {
  if (!first || !second) return [];
  const left = memberKeys(data, first),
    right = memberKeys(data, second);
  return [...left].filter((key) => right.has(key)).sort(compareKeys);
}
export function roomPose(x: number, y: number): [number, number] {
  return [Math.max(0.1, Math.min(0.9, x)), Math.max(0.15, Math.min(0.85, y))];
}
export function noteDraft(data: Data, room: Workspace): Draft {
  const note = data.notes?.find((n) => n.note_id === room.state.note_id);
  const mark = data.annotations?.find(
    (n) => n.annotation_id === room.annotation,
  );
  const document = data.documents?.find(
    (d) =>
      d.document_id ===
      (note?.document_id || mark?.document_id || room.state.document_id),
  );
  const draft = draftFor(data, freshView(), "save_note", [0, 0, 1]);
  draft.id = room.noteDraft ?? crypto.randomUUID();
  draft.noteId = note?.note_id;
  draft.documentId = document?.document_id;
  draft.annotationId = mark?.annotation_id;
  draft.source =
    note?.source_id ?? document?.source_id ?? data.sources[0]?.id ?? "";
  draft.title = note?.title ?? "";
  draft.content = note?.body ?? mark?.quote_text ?? "";
  draft.revision = note?.revision ?? "";
  draft.referenceId =
    note?.reference_id ??
    mark?.reference_id ??
    document?.reference_id ??
    undefined;
  if (draft.referenceId)
    draft.referenceLocator = note?.reference_locator ?? {
      ...emptyLocator(),
      printed_page: mark?.page_label ?? "",
      pdf_page:
        document?.kind === "pdf"
          ? (note?.page_start ?? mark?.page_number ?? null)
          : null,
      passage: mark?.quote_text ?? "",
    };
  return draft;
}
export function acceptRoomResult(room: Workspace, result?: Result): boolean {
  if (!room.pending || room.pending.operation_id !== result?.operation_id)
    return false;
  room.result = result;
  if (result.status === "saved") {
    if (room.pending.action === "save_view" && result.map_uid) {
      if (!room.state.spheres.some((s) => s.view_uid === result.map_uid))
        room.state.spheres.push({
          view_uid: result.map_uid,
          position: roomPose(0.3 + room.state.spheres.length * 0.3, 0.45),
        });
      room.dirty = true;
    } else {
      room.revision = result.view_revision ?? room.revision;
      room.dirty =
        JSON.stringify(room.state) !== JSON.stringify(room.pending.room_state);
    }
    room.pending = undefined;
  } else if (result.status === "invalid" || result.status === "conflict")
    room.pending = undefined;
  return true;
}
function validWorkspace(item: Workspace): boolean {
  return (
    !!item &&
    typeof item.uid === "string" &&
    typeof item.state?.name === "string" &&
    Array.isArray(item.state.spheres) &&
    item.state.spheres.every(
      (s) =>
        typeof s.view_uid === "string" &&
        Array.isArray(s.position) &&
        s.position.length === 2 &&
        s.position.every((p) => Number.isFinite(p) && p >= 0 && p <= 1),
    ) &&
    ["general", "focus", "compare", "note"].includes(item.mode)
  );
}
export class RoomVault {
  private archive: { active: string; rooms: Record<string, Workspace> };
  private corrupt = false;
  error = "";
  constructor(
    private scope: string,
    initial?: SavedRoom,
  ) {
    this.archive = { active: "", rooms: {} };
    try {
      const raw = localStorage.getItem(this.key());
      if (raw) {
        const parsed = JSON.parse(raw);
        if (
          !parsed ||
          typeof parsed.active !== "string" ||
          !parsed.rooms ||
          Array.isArray(parsed.rooms) ||
          !Object.values(parsed.rooms).every((item) =>
            validWorkspace(item as Workspace),
          )
        )
          throw new Error("Invalid room archive");
        this.archive = parsed;
      }
    } catch {
      this.corrupt = true;
      this.error =
        "No se pudo leer la habitación local. El archivo original se conserva; usa descargar para guardar la sesión actual.";
    }
    if (!this.archive.rooms[this.archive.active])
      this.select(
        initial && !this.corrupt ? fromSavedRoom(initial) : emptyRoom(),
      );
  }
  private key(): string {
    return "mathmongo-rooms-v1-" + this.scope;
  }
  current(): Workspace {
    return this.archive.rooms[this.archive.active];
  }
  get(uid: string): Workspace | undefined {
    return this.archive.rooms[uid];
  }
  all(): Workspace[] {
    return Object.values(this.archive.rooms);
  }
  select(room: Workspace): void {
    this.archive.active = room.uid;
    this.archive.rooms[room.uid] = room;
    this.save();
  }
  save(): void {
    if (this.corrupt) return;
    try {
      localStorage.setItem(this.key(), JSON.stringify(this.archive));
    } catch {
      this.error =
        "Almacenamiento local no disponible; conserva una descarga de la habitación antes de cerrar.";
    }
  }
}
