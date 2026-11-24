/** Explicit academic metadata controls; never infer a form from a MongoDB record. */
import { referenceAccessDate } from "./reference-draft";
export type CatalogKind = "source" | "reference" | "document";
export type CatalogRecord = Record<string, unknown> & {
  revision: string;
  status: string;
  source_ids?: string[];
};
export const sourceTypes = {
  book: "Libro",
  article: "Artículo",
  thesis: "Tesis",
  web: "Página web",
  documentation: "Documentación",
  course: "Curso",
  corpus: "Corpus",
  report: "Informe",
  project: "Proyecto",
  bibliographic_collection: "Colección bibliográfica",
  other: "Otra fuente",
};
const referenceTypes = {
  book: "Libro",
  article: "Artículo",
  chapter: "Capítulo",
  thesis: "Tesis",
  web: "Página web",
  report: "Informe",
  proceedings: "Actas",
  course: "Curso",
  misc: "Otro documento",
  other: "Otra referencia",
};
export type MetadataField = {
  key: string;
  label: string;
  multiline?: boolean;
  choices?: Record<string, string>;
  type?: string;
  advanced?: boolean;
};
export const metadataFields: Record<CatalogKind, MetadataField[]> = {
  source: [
    { key: "name", label: "Nombre de la fuente" },
    { key: "source_type", label: "Tipo de fuente", choices: sourceTypes },
    { key: "description", label: "Descripción", multiline: true },
    { key: "language", label: "Idioma", advanced: true },
    {
      key: "tags",
      label: "Etiquetas, una por línea",
      multiline: true,
      advanced: true,
    },
    {
      key: "aliases",
      label: "Otros nombres, uno por línea",
      multiline: true,
      advanced: true,
    },
    {
      key: "copyright_status",
      label: "Derechos conocidos",
      advanced: true,
      choices: {
        unknown: "Sin determinar",
        copyrighted: "Con derechos de autor",
        public_domain: "Dominio público",
        licensed: "Con licencia",
      },
    },
    {
      key: "redistribution",
      label: "Redistribución",
      advanced: true,
      choices: {
        ask: "Consultar antes",
        include: "Permitir inclusión",
        metadata_only: "Sólo metadatos",
        exclude: "Excluir",
      },
    },
    { key: "license", label: "Licencia", advanced: true },
    {
      key: "rights_notes",
      label: "Notas de derechos",
      advanced: true,
      multiline: true,
    },
  ],
  reference: [
    { key: "title", label: "Título de la referencia" },
    {
      key: "reference_type",
      label: "Tipo de referencia",
      choices: referenceTypes,
    },
    { key: "author", label: "Autores separados por punto y coma" },
    { key: "year", label: "Año de publicación", type: "number" },
    ...[
      ["doi", "DOI"],
      ["isbn", "ISBN separados por comas"],
      ["url", "URL"],
      ["year_raw", "Año textual"],
      ["journal", "Revista"],
      ["publisher", "Editorial"],
      ["volume", "Volumen"],
      ["number", "Número"],
      ["edition", "Edición"],
      ["language", "Idioma"],
      ["notes", "Notas bibliográficas"],
      ["bibtex_key", "Clave BibTeX"],
      ["publication_pages", "Páginas de la publicación"],
    ].map(([key, label]) => ({ key, label, advanced: true })),
    {
      key: "accessed_at",
      label: "Fecha de consulta",
      type: "date",
      advanced: true,
    },
  ],
  document: [
    { key: "title", label: "Título del documento" },
    { key: "reference_id", label: "Referencia bibliográfica" },
    { key: "description", label: "Descripción", multiline: true },
    { key: "language", label: "Idioma", advanced: true },
    {
      key: "tags",
      label: "Etiquetas, una por línea",
      multiline: true,
      advanced: true,
    },
  ],
};
const text = (value: unknown) =>
  typeof value === "string" || typeof value === "number" ? String(value) : "";
export function catalogValues(
  kind: CatalogKind,
  record: CatalogRecord,
): Record<string, string> {
  const values = Object.fromEntries(
    metadataFields[kind].map((field) => [field.key, text(record[field.key])]),
  );
  for (const key of ["tags", "aliases"])
    if (Array.isArray(record[key]))
      values[key] = (record[key] as unknown[])
        .map((item) =>
          typeof item === "string"
            ? item
            : text((item as { value?: string }).value),
        )
        .join("\n");
  if (kind === "reference") {
    const authors = (record.authors ?? []) as {
      literal?: string;
      family?: string;
      given?: string;
    }[];
    values.author = authors
      .map(
        (author) =>
          author.literal ||
          [author.given, author.family].filter(Boolean).join(" "),
      )
      .join("; ");
    values.isbn = Array.isArray(record.isbn) ? record.isbn.join(", ") : "";
    values.accessed_at = text(record.accessed_at).slice(0, 10);
    const bibtex = record.bibtex as
      | { key?: string; extra?: { pages?: string } }
      | undefined;
    values.bibtex_key = bibtex?.key || "";
    values.publication_pages = bibtex?.extra?.pages || "";
  }
  if (kind === "source") {
    const rights = record.rights_default as Record<string, unknown> | undefined;
    for (const key of ["copyright_status", "redistribution", "license"])
      values[key] = text(rights?.[key]);
    values.rights_notes = text(rights?.notes);
  }
  return values;
}
export function catalogChanges(
  kind: CatalogKind,
  before: CatalogRecord,
  values: Record<string, string>,
): Record<string, unknown> {
  const old = catalogValues(kind, before),
    changes: Record<string, unknown> = {};
  for (const field of metadataFields[kind]) {
    const key = field.key,
      value = values[key];
    if (value === old[key]) continue;
    if (
      [
        "copyright_status",
        "redistribution",
        "license",
        "rights_notes",
      ].includes(key)
    ) {
      changes.rights_default = {
        ...((changes.rights_default || before.rights_default || {}) as object),
        [key === "rights_notes" ? "notes" : key]: value,
      };
    } else if (key === "bibtex_key" || key === "publication_pages") {
      const bibtex = {
        ...((changes.bibtex || before.bibtex || {}) as Record<string, unknown>),
      };
      if (key === "bibtex_key") bibtex.key = value || null;
      else bibtex.extra = { ...((bibtex.extra || {}) as object), pages: value };
      changes.bibtex = bibtex;
    } else if (key === "author")
      changes.authors = value
        .split(";")
        .map((name) => name.trim())
        .filter(Boolean)
        .map((literal) => ({ literal }));
    else if (key === "year") changes.year = value ? Number(value) : null;
    else if (key === "isbn")
      changes.isbn = value
        .split(",")
        .map((item) => item.trim())
        .filter(Boolean);
    else if (key === "tags" || key === "aliases")
      changes[key] = value
        .split("\n")
        .map((item) => item.trim())
        .filter(Boolean);
    else if (key === "accessed_at")
      changes[key] = referenceAccessDate(value, text(before.accessed_at));
    else
      changes[key] =
        value || (["description", "name", "title"].includes(key) ? "" : null);
  }
  return changes;
}
export function rebaseCatalog(
  kind: CatalogKind,
  before: CatalogRecord,
  values: Record<string, string>,
  current: CatalogRecord,
): Record<string, string> {
  const original = catalogValues(kind, before),
    next = catalogValues(kind, current);
  for (const key of Object.keys(values))
    if (values[key] !== original[key]) next[key] = values[key];
  return next;
}
