import { beforeEach, afterEach, expect, it, vi } from "vitest";
import { discoverConceptDrafts } from "../src/study/ConceptDraftRecovery";
import { DraftVault } from "../src/knowledge-map/drafts";
import type { Draft } from "../src/knowledge-map/model";
const copy = {
  id: "edit-a",
  action: "edit",
  title: "Trabajo",
  content: "\\macro{á}\r\n",
} as Draft;
beforeEach(() => localStorage.clear());
afterEach(() => vi.restoreAllMocks());
it("finds a closed window's exact draft without altering any archive or crossing library boundaries", () => {
  const old = new DraftVault("mine", "study-concepts-window-closed");
  old.put({ ...copy });
  new DraftVault("other", "study-concepts-window-closed").put({ ...copy });
  const before = { ...localStorage };
  const result = discoverConceptDrafts("mine", "current", copy.id!);
  expect(result.copies).toHaveLength(1);
  expect(result.copies[0].draft.content).toBe(copy.content);
  expect({ ...localStorage }).toEqual(before);
});
it("offers legacy copies explicitly but ignores completed, unrelated and current-window work", () => {
  const current = new DraftVault("mine", "study-concepts-window-live");
  current.put({ ...copy });
  new DraftVault("mine", "study-concepts-window-finished").put({
    ...copy,
    completed: true,
  });
  new DraftVault("mine", "study-concepts-window-other").put({
    ...copy,
    id: "edit-other",
  });
  new DraftVault("mine", "study-concepts").put({ ...copy });
  const result = discoverConceptDrafts("mine", current.key, copy.id!);
  expect(result.copies.map((value) => value.archive)).toEqual([
    "mathmongo-drafts-v2-mine-study-concepts",
  ]);
});
it("reports unreadable archives and preserves their exact bytes while offering healthy copies", () => {
  const key = "mathmongo-drafts-v2-mine-study-concepts-window-broken";
  localStorage.setItem(key, "{broken");
  new DraftVault("mine", "study-concepts").put({ ...copy });
  const result = discoverConceptDrafts("mine", "current", copy.id!);
  expect(result.unavailable).toBe(true);
  expect(result.copies).toHaveLength(1);
  expect(localStorage.getItem(key)).toBe("{broken");
});
it("reports denied storage without promising recovery", () => {
  vi.spyOn(Storage.prototype, "key").mockImplementation(() => {
    throw new Error("Denied");
  });
  localStorage.setItem("dummy", "value");
  expect(discoverConceptDrafts("mine", "current", copy.id!)).toEqual({
    copies: [],
    unavailable: true,
  });
});
