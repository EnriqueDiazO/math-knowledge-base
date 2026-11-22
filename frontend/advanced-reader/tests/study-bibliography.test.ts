import { afterEach, beforeEach, expect, it, vi } from "vitest";
import {
  fireEvent,
  getByRole,
  getByLabelText,
  getAllByRole,
} from "@testing-library/dom";
import {
  consumeBibliography,
  renderBibliography,
  emptyLocator,
  referenceLabel,
} from "../src/knowledge-map/bibliography";
import type {
  BibliographyDraft,
  ReferenceData,
} from "../src/knowledge-map/bibliography";
import { draftFor, freshView, intention } from "../src/knowledge-map/model";
const ref = (): ReferenceData => ({
  reference_id: "ref_" + crypto.randomUUID(),
  title: '<img onerror="bad()">Título',
  authors: [{ given: "V. I.", family: "Nyaga" }],
  year: 1977,
  reference_type: "article",
  edition: "Traducción",
  isbn: [],
  bibtex: { key: "ClaveEstable", extra: { pages: "228-231" } },
  provenance: {
    warnings: ["Dato incompleto"],
    external_lookup: {
      provider: "crossref",
      record_kind: "article",
      retrieved_at: "2026-11-22T00:00:00Z",
    },
  },
});
const state = (): BibliographyDraft => ({
  open: true,
  query: "10.1007/BF01106749",
  title: "",
  author: "",
  status: "idle",
  candidates: [],
});
let parent: HTMLDivElement;
let dispose: (() => void) | undefined;
beforeEach(() => {
  parent = document.createElement("div");
  document.body.append(parent);
  HTMLDialogElement.prototype.showModal = function () {
    this.open = true;
  };
  HTMLDialogElement.prototype.close = function () {
    this.open = false;
  };
});
afterEach(() => {
  dispose?.();
  parent.remove();
  vi.restoreAllMocks();
});

it("rejects response A after B and retains corrected metadata after provider failures", () => {
  const draft = state();
  const reference = ref();
  draft.selected = { reference_data: reference };
  draft.pending = "B";
  draft.status = "searching";
  expect(
    consumeBibliography(draft, {
      request_id: "A",
      status: "found",
      candidates: [{ reference_data: ref() }],
    }),
  ).toBeUndefined();
  expect(draft.pending).toBe("B");
  expect(draft.selected.reference_data).toBe(reference);
  consumeBibliography(draft, { request_id: "B", status: "unavailable" });
  expect(draft.selected.reference_data).toBe(reference);
  expect(draft.status).toBe("unavailable");
  draft.pending = "C";
  expect(
    consumeBibliography(draft, {
      request_id: "C",
      status: "saved",
      reference_data: reference,
    }),
  ).toEqual(reference);
  expect(draft.open).toBe(false);
});

it("edits declared metadata, sends only explicit identifier/title actions and keeps HTML inert", () => {
  const draft = state();
  draft.candidates = [{ reference_data: ref(), edition_ids: ["OL123M"] }];
  const send = vi.fn(),
    changed = vi.fn(),
    close = vi.fn();
  dispose = renderBibliography(parent, draft, send, "source", changed, close);
  expect(parent.querySelector("img")).toBeNull();
  fireEvent.click(
    getByRole(parent, "button", { name: "Revisar esta propuesta" }),
  );
  fireEvent.input(getByLabelText(parent, "Título de la referencia"), {
    target: { value: "Corrección manual" },
  });
  fireEvent.input(getByLabelText(parent, "Año de la edición/publicación"), {
    target: { value: "2006" },
  });
  fireEvent.input(getByLabelText(parent, "Traductores"), {
    target: { value: "Traductora declarada" },
  });
  expect(draft.selected?.reference_data.title).toBe("Corrección manual");
  expect(send).not.toHaveBeenCalled();
  fireEvent.click(
    getByRole(parent, "button", { name: "Guardar ficha y citar" }),
  );
  const payload = send.mock.calls[0][0];
  expect(payload).toMatchObject({
    action: "save",
    source_id: "source",
    reference_data: {
      title: "Corrección manual",
      year: 2006,
      bibtex: {
        key: "ClaveEstable",
        extra: { pages: "228-231", translator: "Traductora declarada" },
      },
    },
  });
  expect(payload).not.toHaveProperty("note");
  expect(payload).not.toHaveProperty("pdf");
  expect(payload.request_id).toBe(draft.pending);
});

it("uses an existing ID without writing its metadata and supports a manual fallback", () => {
  const draft = state();
  const existing = ref();
  draft.candidates = [{ reference_data: existing, existing: true }];
  const send = vi.fn();
  dispose = renderBibliography(
    parent,
    draft,
    send,
    "source",
    () => {},
    () => {},
  );
  fireEvent.click(
    getByRole(parent, "button", { name: "Usar referencia existente" }),
  );
  expect(
    parent.querySelector('[aria-label="Título de la referencia"]'),
  ).toBeNull();
  fireEvent.click(
    getByRole(parent, "button", { name: "Guardar ficha y citar" }),
  );
  expect(send.mock.calls[0][0]).toMatchObject({
    action: "save",
    existing_reference_id: existing.reference_id,
  });
  expect(send.mock.calls[0][0]).not.toHaveProperty("reference_data");
  fireEvent.click(getByRole(parent, "button", { name: "Ficha manual" }));
  expect(draft.selected?.reference_data.reference_id).not.toBe(
    existing.reference_id,
  );
  expect(draft.selected?.reference_data.title).toBe("");
});

it("consults a selected edition and title/author only on explicit buttons", () => {
  const draft = state();
  draft.candidates = [{ reference_data: ref(), edition_ids: ["OL123M"] }];
  const send = vi.fn();
  dispose = renderBibliography(
    parent,
    draft,
    send,
    "source",
    () => {},
    () => {},
  );
  fireEvent.input(getByLabelText(parent, "Título del libro"), {
    target: { value: "Obra" },
  });
  fireEvent.input(getByLabelText(parent, "Autor del libro"), {
    target: { value: "Autora" },
  });
  expect(send).not.toHaveBeenCalled();
  fireEvent.click(getByRole(parent, "button", { name: "Buscar libros" }));
  expect(send.mock.calls[0][0]).toMatchObject({
    action: "title",
    query: "Obra",
    author: "Autora",
  });
  fireEvent.click(
    getByRole(parent, "button", { name: "Consultar edición OL123M" }),
  );
  expect(send.mock.calls[1][0]).toMatchObject({
    action: "edition",
    query: "OL123M",
  });
  expect(getAllByRole(parent, "status")[0].textContent).toContain("Buscando");
});

it("keeps printed and PDF page independent when saving either notes or concepts", () => {
  const data = {
    scope: "citation",
    nodes: [],
    edges: [],
    sources: [{ id: "source", name: "Source" }],
    concept_types: [],
    relation_types: [],
  };
  const draft = draftFor(data, freshView(), "create", [0, 0, 1]);
  draft.referenceId = ref().reference_id;
  draft.referenceLocator = {
    ...emptyLocator(),
    printed_page: "xii",
    pdf_page: 18,
    theorem: "2.1",
  };
  expect(intention(draft, "operation")).toMatchObject({
    reference_id: draft.referenceId,
    reference_locator: { printed_page: "xii", pdf_page: 18 },
  });
  draft.action = "save_note";
  expect(intention(draft, "operation").reference_locator?.printed_page).toBe(
    "xii",
  );
  expect(referenceLabel({ reference_id: "id" })).toBe("Sin título");
});
