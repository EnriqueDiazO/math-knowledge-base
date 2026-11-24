import { mockWindowLocks } from "./web-locks-support";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { DraftVault } from "../src/knowledge-map/drafts";
import { conceptDraftStorage } from "../src/study/concept-drafts";
import { rebaseConcept } from "../src/study/concept-rebase";
import type { ConceptDetail } from "../src/study/api";
import type { Draft } from "../src/knowledge-map/model";
beforeEach(() => {
  mockWindowLocks();
  localStorage.clear();
  sessionStorage.clear();
});
afterEach(() => vi.restoreAllMocks());
const base: ConceptDetail = {
  id: "id",
  key: "id@Fuente",
  tipo: "definicion",
  source: "Fuente",
  titulo: "Original",
  contenido_latex: "Fuente original",
  comentario: "Comentario",
  categorias: ["Uno"],
  revision: "old",
  reference_id: undefined,
  source_id: "source-owned",
  passages: [],
  reference_locator: null,
};
const local = {
  id: "edit-id",
  action: "edit",
  title: "Original",
  content: "Fuente local",
  comment: "Comentario",
  categories: "Uno",
  revision: "old",
  referenceId: undefined,
  referenceLocator: undefined,
  document: { json: { type: "doc" }, sourceMode: true },
} as Draft;
it("does not let one tab's confirmed save erase another tab's recoverable draft", async () => {
  const first = conceptDraftStorage("library");
  await first.ready;
  first.current.put({ ...local });
  sessionStorage.clear();
  const second = conceptDraftStorage("library");
  await second.ready;
  second.current.put({ ...local, content: "Otra pestaña" });
  first.current.discard(local.id!);
  expect(
    new DraftVault(
      "library",
      "study-concepts-window-" +
        sessionStorage.getItem("mathmongo-concept-window-v1"),
    ).get(local.id!)?.content,
  ).toBe("Otra pestaña");
  expect(second.current.key).not.toBe(first.current.key);
});
it("recovers the same tab across remounts and preserves the previous unpartitioned archive", async () => {
  const legacy = new DraftVault("library", "study-concepts");
  legacy.put({ ...local });
  const before = localStorage.getItem(legacy.key);
  const first = conceptDraftStorage("library");
  await first.ready;
  expect(first.legacy.get(local.id!)?.content).toBe("Fuente local");
  first.current.put({ ...local, content: "Versión de esta ventana" });
  expect(conceptDraftStorage("library").current.get(local.id!)?.content).toBe(
    "Versión de esta ventana",
  );
  expect(localStorage.getItem(legacy.key)).toBe(before);
});
it("marks failed session storage as unrecoverable rather than promising reload safety", async () => {
  vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => {
    throw new Error("Denied");
  });
  const storage = conceptDraftStorage("library");
  await storage.ready;
  expect(storage.recoverable).toBe(false);
});
it("rebases only deliberately changed fields and adopts untouched remote metadata", () => {
  const remote = {
    ...base,
    titulo: "Remoto",
    comentario: "Cambio remoto",
    categorias: ["Remota"],
    revision: "new",
    contenido_latex: "Fuente remota",
  };
  const next = rebaseConcept(local, base, remote);
  expect(next).toMatchObject({
    title: "Remoto",
    comment: "Cambio remoto",
    categories: "Remota",
    content: "Fuente local",
    revision: "new",
  });
  expect(next.document).toEqual(local.document);
  expect(local.revision).toBe("old");
});
it("keeps locally changed metadata and uses remote body only when local source is untouched", () => {
  const remote = {
    ...base,
    contenido_latex: "Nueva fuente remota",
    revision: "new",
  };
  const next = rebaseConcept(
    {
      ...local,
      title: "Mi título",
      content: base.contenido_latex,
      comment: "Mi comentario",
      categories: "Mis categorías",
    },
    base,
    remote,
  );
  expect(next).toMatchObject({
    title: "Mi título",
    content: "Nueva fuente remota",
    comment: "Mi comentario",
    categories: "Mis categorías",
  });
  expect(next.document).toBeUndefined();
});
it("rejects a different identity before changing a draft", () => {
  expect(() =>
    rebaseConcept(local, base, { ...base, key: "other@Fuente" }),
  ).toThrow("identidad");
  expect(() =>
    rebaseConcept(local, base, { ...base, tipo: "teorema" }),
  ).toThrow("identidad");
  expect(() => rebaseConcept(local, base, { ...base, source: "Otra" })).toThrow(
    "identidad",
  );
});

it("allocates another identity when another document already owns the copied session", async () => {
  const previousId = crypto.randomUUID();
  sessionStorage.setItem("mathmongo-concept-window-v1", previousId);
  const previous = new DraftVault(
    "library",
    "study-concepts-window-" + previousId,
  );
  previous.put({ ...local });
  const raw = localStorage.getItem(previous.key);
  vi.mocked(navigator.locks.request).mockImplementationOnce(
    (_name: string, _options: unknown, callback: (lock: null) => unknown) =>
      Promise.resolve(callback(null)) as Promise<never>,
  );
  const copied = conceptDraftStorage("library");
  await copied.ready;
  expect(copied.recoverable).toBe(true);
  expect(copied.current.key).not.toBe(previous.key);
  expect(copied.current.get(local.id!)?.content).toBe(local.content);
  expect(localStorage.getItem(previous.key)).toBe(raw);
});
it("does not promise isolation when the browser denies a window lease", async () => {
  vi.mocked(navigator.locks.request).mockRejectedValueOnce(new Error("Denied"));
  const storage = conceptDraftStorage("library");
  await storage.ready;
  expect(storage.recoverable).toBe(false);
});
it("requires browser window ownership instead of silently falling back to shared drafts", async () => {
  Object.defineProperty(navigator, "locks", {
    configurable: true,
    value: undefined,
  });
  const storage = conceptDraftStorage("library");
  await storage.ready;
  expect(storage.recoverable).toBe(false);
});
it("retains locally edited bibliographic fields while adopting a new revision", () => {
  const locator = { printed_page: "32" } as NonNullable<
    Draft["referenceLocator"]
  >;
  const next = rebaseConcept(
    { ...local, referenceId: "my-reference", referenceLocator: locator },
    base,
    { ...base, revision: "remote", reference_id: "other-reference" },
  );
  expect(next.referenceId).toBe("my-reference");
  expect(next.referenceLocator).toEqual(locator);
  expect(next.revision).toBe("remote");
});
