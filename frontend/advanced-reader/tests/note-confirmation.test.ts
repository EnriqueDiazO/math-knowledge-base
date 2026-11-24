import { describe, expect, it } from "vitest";
import { noteMatchesIntent } from "../src/study/note-confirmation";
import { emptyLocator } from "../src/knowledge-map/bibliography";
import type { NoteDetail } from "../src/study/api";
import type { Intent } from "../src/knowledge-map/model";
const sent: Intent = {
  action: "save_note",
  operation_id: "operation",
  note_id: "note",
  source_id: "source",
  document_id: "document",
  titulo: " Title ",
  contenido_latex: "\n  Body $x$\n",
  reference_id: "reference",
  reference_locator: { ...emptyLocator(), printed_page: "23" },
};
const note = {
  note_id: "note",
  source_id: "source",
  document_id: "document",
  title: "Title",
  body: sent.contenido_latex,
  reference_id: "reference",
  reference_locator: sent.reference_locator,
  revision: "confirmed",
} as NoteDetail;
describe("coherent note acknowledgement", () => {
  it("confirms the exact submitted document and citation, including significant whitespace", () =>
    expect(noteMatchesIntent(note, sent, "note")).toBe(true));
  it.each([
    "body",
    "title",
    "source_id",
    "document_id",
    "reference_id",
    "note_id",
  ] as const)(
    "rejects a concurrent %s change without adopting its revision",
    (field) =>
      expect(
        noteMatchesIntent({ ...note, [field]: "foreign" }, sent, "note"),
      ).toBe(false),
  );
  it("keeps printed and PDF page changes distinct and rejects an unrelated acknowledgement", () => {
    expect(
      noteMatchesIntent(
        {
          ...note,
          reference_locator: {
            ...emptyLocator(),
            printed_page: "23",
            pdf_page: 24,
          },
        },
        sent,
        "note",
      ),
    ).toBe(false);
    expect(noteMatchesIntent(note, sent, "different")).toBe(false);
  });
});
