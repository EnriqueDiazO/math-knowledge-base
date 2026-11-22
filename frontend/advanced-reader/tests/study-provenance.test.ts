import { expect, it, vi } from "vitest";
import { getByRole, fireEvent } from "@testing-library/dom";
import {
  conceptSources,
  renderConceptSources,
} from "../src/knowledge-map/provenance";
import type { Data, Node } from "../src/knowledge-map/model";
const node: Node = {
  key: "a@Uno",
  id: "a",
  source: "Uno",
  titulo: "Título repetido",
  tipo: "nota",
  contenido_latex: "",
  comentario: "",
  categorias: [],
  revision: "r",
  reference_id: "ref",
};
const data = (): Data => ({
  scope: "db",
  nodes: [node, { ...node, key: "a@Dos", source: "Dos" }],
  edges: [],
  sources: [],
  concept_types: [],
  relation_types: [],
  documents: [
    {
      document_id: "doc",
      source_id: "source",
      reference_id: "ref",
      kind: "pdf",
      title: "Edición",
    },
  ],
  annotations: [
    {
      annotation_id: "mark",
      document_id: "doc",
      source_id: "source",
      reference_id: "ref",
      page_number: 18,
      page_label: "xii",
      quote_text: '<img onerror="bad()">Pasaje exacto',
      body: "",
      kind: "highlight",
    },
  ],
  evidence: [
    {
      concept_legacy_id: "a",
      concept_legacy_source: "Uno",
      source_id: "source",
      document_id: null,
      note_id: null,
      annotation_id: "mark",
      reference_id: "ref",
      page_number: 18,
      link_type: "supported_by",
    },
  ],
});
it("uses exact concept/source and annotation IDs, preserving both locators without mixing a title twin", () => {
  const graph = data();
  const links = conceptSources(node, graph);
  expect(links).toHaveLength(1);
  expect(links[0]).toMatchObject({
    annotationId: "mark",
    documentId: "doc",
    printedPage: "xii",
    pdfPage: 18,
    exact: true,
  });
  const other = conceptSources({ ...node, source: "Dos" }, graph);
  expect(other[0].exact).toBe(false);
  expect(other[0].annotationId).toBeUndefined();
});
it("renders provider/annotation text inertly and sends only logical navigation IDs", () => {
  const parent = document.createElement("div"),
    send = vi.fn();
  renderConceptSources(parent, node, data(), send);
  expect(parent.querySelector("img")).toBeNull();
  expect(parent.querySelector("blockquote")?.textContent).toContain("<img");
  fireEvent.click(
    getByRole(parent, "button", { name: "Volver al pasaje de la anotación" }),
  );
  expect(send).toHaveBeenCalledWith("open_source", {
    document_id: "doc",
    annotation_id: "mark",
  });
});
it("keeps a general bibliography link general even when a manually supplied PDF page exists", () => {
  const graph = data();
  graph.evidence = [];
  const links = conceptSources(
    {
      ...node,
      reference_locator: {
        printed_page: "42",
        pdf_page: 999,
        chapter: "",
        section: "",
        theorem: "",
        passage: "",
      },
    },
    graph,
  );
  expect(links[0]).toMatchObject({
    exact: false,
    pdfPage: null,
    printedPage: "",
  });
  graph.documents![0].reference_id = "different-edition";
  expect(conceptSources(node, graph)).toEqual([]);
});
