import { afterEach, expect, it, vi } from "vitest";
import {
  DraftVault,
  persistedView,
  storeView,
} from "../src/knowledge-map/drafts";
import { draftFor, freshView } from "../src/knowledge-map/model";
afterEach(() => {
  localStorage.clear();
  vi.restoreAllMocks();
});
const draft = () =>
  draftFor(
    {
      scope: "scope",
      nodes: [],
      edges: [],
      sources: [],
      concept_types: [],
      relation_types: [],
    },
    freshView(),
    "create",
    [0, 0, 1],
  );
it("isolates databases, maps and distinct drafts, retaining incomplete content after reload", () => {
  const vault = new DraftVault("db-a", "map-a"),
    first = { ...draft(), title: "Primero", content: "Texto $\\frac{" };
  vault.put(first);
  vault.put({ ...draft(), title: "Segundo" });
  first.content = "Cambio externo al snapshot";
  const recovered = new DraftVault("db-a", "map-a");
  expect(recovered.all()).toHaveLength(2);
  expect(recovered.get(first.id!)?.content).toBe("Texto $\\frac{");
  expect(new DraftVault("db-a", "map-b").all()).toEqual([]);
  expect(new DraftVault("db-b", "map-a").all()).toEqual([]);
  recovered.complete(recovered.get(first.id!)!);
  expect(recovered.all()).toHaveLength(1);
  recovered.discard(recovered.all()[0].id!);
  expect(recovered.all()).toEqual([]);
});
it.each(["null", "[]", '{"broken":{"title":"Texto sin contrato"}}', "{broken"])(
  "preserves an unreadable archive and warns instead of overwriting it: %s",
  (raw) => {
    const key = "mathmongo-drafts-v2-db-map";
    localStorage.setItem(key, raw);
    const vault = new DraftVault("db", "map");
    expect(vault.available).toBe(false);
    vault.put(draft());
    expect(vault.all()).toHaveLength(1);
    expect(localStorage.getItem(key)).toBe(raw);
    vault.discard(vault.all()[0].id!);
    expect(localStorage.getItem(key)).toBe(raw);
  },
);
it("retains the in-memory draft on quota failure and reports a failed view persistence", () => {
  const vault = new DraftVault("db", "map");
  vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => {
    throw new Error("quota");
  });
  vault.put(draft());
  expect(vault.available).toBe(false);
  expect(vault.all()).toHaveLength(1);
  vault.discard(vault.all()[0].id!);
  expect(vault.all()).toEqual([]);
  expect(storeView("db", freshView())).toBe(false);
});
it("recovers a complete local camera snapshot and handles malformed view JSON", () => {
  const view = freshView();
  view.camera.yaw = 1.5;
  expect(storeView("db", view)).toBe(true);
  expect(persistedView("db")).toEqual(view);
  localStorage.setItem("mathmongo-map-v2-db", "broken");
  expect(persistedView("db")).toBeUndefined();
});
