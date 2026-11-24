import { describe, expect, it } from "vitest";
import {
  catalogChanges,
  catalogValues,
  rebaseCatalog,
  type CatalogRecord,
} from "../src/study/catalog-fields";
const source = {
  revision: "old",
  status: "active",
  name: "Original",
  source_type: "book",
  description: "Descripción",
  tags: ["familia, literal"],
  aliases: [{ value: "Nombre anterior" }],
  rights_default: {
    copyright_status: "unknown",
    redistribution: "ask",
    license: "Original",
    notes: "Conservar",
  },
} as CatalogRecord;
describe("explicit metadata changes and conflict reconciliation", () => {
  it("sends no update for untouched fields and keeps comma-containing tags intact", () => {
    const values = catalogValues("source", source);
    expect(catalogChanges("source", source, values)).toEqual({});
    expect(
      catalogChanges("source", source, { ...values, name: "Corregido" }),
    ).toEqual({ name: "Corregido" });
    expect(
      catalogChanges("source", source, { ...values, license: "Nueva" }),
    ).toEqual({
      rights_default: {
        ...(source.rights_default as object),
        license: "Nueva",
      },
    });
  });
  it("preserves structured authors, BibTeX extensions and full dates unless explicitly changed", () => {
    const reference = {
      revision: "r",
      status: "active",
      title: "Título",
      authors: [{ given: "Emmy", family: "Noether", orcid: "kept" }],
      year: 1918,
      isbn: ["978-1"],
      accessed_at: "2026-11-20T12:34:56Z",
      bibtex: { key: "Noether", extra: { pages: "1-9", custom: "kept" } },
    } as CatalogRecord;
    const values = catalogValues("reference", reference);
    expect(
      catalogChanges("reference", reference, { ...values, title: "Nuevo" }),
    ).toEqual({ title: "Nuevo" });
    expect(
      catalogChanges("reference", reference, {
        ...values,
        publication_pages: "20-30",
      }),
    ).toEqual({
      bibtex: { key: "Noether", extra: { pages: "20-30", custom: "kept" } },
    });
    expect(
      catalogChanges("reference", reference, {
        ...values,
        author: "Ada; Alan",
        year: "",
        isbn: "",
        accessed_at: "",
      }),
    ).toEqual({
      authors: [{ literal: "Ada" }, { literal: "Alan" }],
      year: null,
      isbn: [],
      accessed_at: null,
    });
  });
  it("rebases only locally edited fields, leaving other-window changes intact", () => {
    const current = {
      ...source,
      revision: "new",
      description: "Otra ventana",
      tags: ["Cambios recientes"],
    };
    const merged = rebaseCatalog(
      "source",
      source,
      { ...catalogValues("source", source), name: "Mi cambio" },
      current,
    );
    expect(merged.description).toBe("Otra ventana");
    expect(merged.tags).toBe("Cambios recientes");
    expect(catalogChanges("source", current, merged)).toEqual({
      name: "Mi cambio",
    });
  });
});
