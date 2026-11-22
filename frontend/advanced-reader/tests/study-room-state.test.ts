import { beforeEach, expect, it } from "vitest";
import {
  emptyRoom,
  RoomVault,
  fromSavedRoom,
  noteDraft,
  acceptRoomResult,
  sharedConcepts,
  roomPose,
} from "../src/knowledge-map/room-state";
import { freshView, studyState } from "../src/knowledge-map/model";
import type { Data, SavedView } from "../src/knowledge-map/model";
const data = (): Data => ({
  scope: "db",
  sources: [{ id: "source", name: "Fuente" }],
  concept_types: ["nota"],
  relation_types: [],
  edges: [],
  nodes: ["a@Uno", "a@Dos", "b@Uno"].map((key) => ({
    key,
    id: key.split("@")[0],
    source: key.split("@")[1],
    titulo: "Mismo título",
    tipo: "nota",
    contenido_latex: "Cuerpo",
    comentario: "",
    categorias: [],
    revision: "r",
  })),
});
const view = (members: string[], uid = crypto.randomUUID()): SavedView => ({
  uid,
  name: uid,
  revision: "r",
  state: { ...studyState(freshView()), members },
});
beforeEach(() => localStorage.clear());
it("uses canonical IDs across memberships, never identical titles or proximity", () => {
  const graph = data(),
    left = view(["a@Uno", "a@Dos"]),
    right = view(["a@Uno", "b@Uno"]);
  expect(sharedConcepts(graph, left, right)).toEqual(["a@Uno"]);
  expect(sharedConcepts(graph, left, view(["b@Uno"]))).toEqual([]);
  expect(sharedConcepts(graph, left, undefined)).toEqual([]);
  expect(sharedConcepts(graph, view(["removed"]), right)).toEqual([]);
});
it("recovers independent rooms and database scopes without changing referenced graphs", () => {
  const first = emptyRoom(),
    second = emptyRoom(),
    sphere = view(["a@Uno"]);
  first.state.spheres = [{ view_uid: sphere.uid, position: [0.2, 0.5] }];
  const original = structuredClone(sphere);
  const vault = new RoomVault("dbA");
  vault.select(first);
  first.state.spheres[0].position = roomPose(0.8, 0.7);
  vault.save();
  vault.select(second);
  vault.select(first);
  expect(new RoomVault("dbA").current().state.spheres[0].position).toEqual([
    0.8, 0.7,
  ]);
  expect(new RoomVault("dbB").current().uid).not.toBe(first.uid);
  expect(sphere).toEqual(original);
});
it("preserves unreadable local archives while allowing a recoverable memory session", () => {
  localStorage.setItem("mathmongo-rooms-v1-db", "{");
  const vault = new RoomVault("db");
  vault.current().state.name = "Trabajo en memoria";
  vault.save();
  expect(vault.error).toContain("original se conserva");
  expect(localStorage.getItem("mathmongo-rooms-v1-db")).toBe("{");
  expect(vault.current().state.name).toBe("Trabajo en memoria");
});
it("restores saved poses without aliasing server state", () => {
  const original = emptyRoom();
  const saved = {
    uid: original.uid,
    revision: "server",
    state: original.state,
  };
  const recovered = fromSavedRoom(saved);
  recovered.state.name = "Cambio local";
  expect(saved.state.name).not.toBe(recovered.state.name);
  expect(recovered.revision).toBe("server");
});
it("keeps annotation quote and printed/PDF locator independent in a note draft", () => {
  const graph = data(),
    room = emptyRoom();
  graph.documents = [
    {
      document_id: "doc",
      source_id: "source",
      reference_id: "ref",
      kind: "pdf",
      title: "Edición",
    },
  ];
  graph.annotations = [
    {
      annotation_id: "mark",
      document_id: "doc",
      source_id: "source",
      reference_id: "ref",
      page_number: 18,
      page_label: "xii",
      quote_text: "Pasaje exacto",
      body: "Comentario",
      kind: "highlight",
    },
  ];
  room.state.document_id = "doc";
  room.annotation = "mark";
  room.noteDraft = "draft";
  const draft = noteDraft(graph, room);
  expect(draft).toMatchObject({
    id: "draft",
    action: "save_note",
    content: "Pasaje exacto",
    documentId: "doc",
    annotationId: "mark",
    referenceId: "ref",
  });
  expect(draft.referenceLocator).toMatchObject({
    printed_page: "xii",
    pdf_page: 18,
    passage: "Pasaje exacto",
  });
  graph.documents[0].kind = "web";
  expect(noteDraft(graph, room).referenceLocator?.pdf_page).toBeNull();
});
it("opens canonical saved notes without replacing their explicit locator", () => {
  const graph = data(),
    room = emptyRoom();
  graph.notes = [
    {
      note_id: "note",
      source_id: "source",
      document_id: null,
      reference_id: "ref",
      title: "Nota",
      body: "Texto con $x$",
      revision: "rev",
      page_start: null,
      page_end: null,
      tags: [],
      reference_locator: {
        printed_page: "42",
        pdf_page: null,
        chapter: "2",
        section: "",
        theorem: "",
        passage: "",
      },
    },
  ];
  room.state.note_id = "note";
  expect(noteDraft(graph, room)).toMatchObject({
    title: "Nota",
    content: "Texto con $x$",
    noteId: "note",
    revision: "rev",
    referenceLocator: { printed_page: "42" },
  });
});
it("ignores stale acknowledgements and reconciles a created sphere without changing room revision", () => {
  const room = emptyRoom();
  room.revision = "room-old";
  const uid = crypto.randomUUID();
  room.pending = { operation_id: "op", action: "save_view", map_uid: uid };
  expect(
    acceptRoomResult(room, {
      operation_id: "other",
      status: "saved",
      message: "Old",
    }),
  ).toBe(false);
  acceptRoomResult(room, {
    operation_id: "op",
    status: "saved",
    message: "Vista",
    map_uid: uid,
    view_revision: "view-new",
  });
  expect(room.revision).toBe("room-old");
  expect(room.state.spheres[0].view_uid).toBe(uid);
  expect(room.dirty).toBe(true);
});
it("retains changes made after a room save was submitted", () => {
  const room = emptyRoom();
  room.dirty = true;
  room.pending = {
    operation_id: "op",
    action: "save_room",
    room_state: structuredClone(room.state),
  };
  room.state.name = "Nombre posterior";
  acceptRoomResult(room, {
    operation_id: "op",
    status: "saved",
    message: "Guardada",
    view_revision: "new",
  });
  expect(room.state.name).toBe("Nombre posterior");
  expect(room.revision).toBe("new");
  expect(room.dirty).toBe(true);
});
it("freezes a view submission independently of later drags and membership changes", () => {
  const state = freshView();
  state.points = { "a@Uno": [0, 0, 1] };
  state.members = ["a@Uno"];
  const submitted = studyState(state);
  state.points["a@Uno"] = [1, 0, 0];
  state.members.push("b@Uno");
  expect(submitted.points["a@Uno"]).toEqual([0, 0, 1]);
  expect(submitted.members).toEqual(["a@Uno"]);
});
