/** Region bodies remain canonical LaTeX; opaque document extensions remain untouched. */
import type { EditorSnapshot } from "../knowledge-map/document-editor";
export type Family = "cornell" | "cpi";
export const regions = {
  cornell: [
    ["cue", "Ideas y preguntas"],
    ["main", "Desarrollo"],
    ["summary", "Síntesis"],
  ],
  cpi: [
    ["comprehension", "Comprensión"],
    ["production", "Producción"],
    ["integration", "Integración"],
  ],
} as const;
export type Region = { heading: string; latex: string; image_ids: string[] };
export type StructuredPage = {
  page_id?: string;
  order?: number;
  page_number?: number;
  [key: string]: unknown;
};
export type StructuredDocument = {
  schema_version: number;
  template_id: string;
  pages: StructuredPage[];
  [key: string]: unknown;
};
export type Metadata = {
  title?: string;
  date?: string;
  project?: string;
  context?: string;
  tags?: string[];
};
export type StructuredDetail = {
  note_id: string;
  revision: string;
  family: Family;
  metadata: Metadata;
  document: StructuredDocument;
  latex_body: string;
};
export type StructuredDraft = {
  metadata: string;
  document: string;
  original: string;
  revision: string;
  snapshots: string;
  origins: string;
  keys: string;
  pending: string;
  request_id: string;
};
export function sameStructuredValue(left: unknown, right: unknown): boolean {
  if (left === right) return true;
  if (!left || !right || typeof left !== "object" || typeof right !== "object")
    return false;
  if (Array.isArray(left) || Array.isArray(right))
    return (
      Array.isArray(left) &&
      Array.isArray(right) &&
      left.length === right.length &&
      left.every((value, index) => sameStructuredValue(value, right[index]))
    );
  const a = left as Record<string, unknown>,
    b = right as Record<string, unknown>;
  return (
    Object.keys(a).length === Object.keys(b).length &&
    Object.keys(a).every(
      (key) => Object.hasOwn(b, key) && sameStructuredValue(a[key], b[key]),
    )
  );
}
export function emptyPage(family: Family): StructuredPage {
  return {
    ...(family === "cornell"
      ? { page_id: crypto.randomUUID(), order: 1, source_refs: [] }
      : { page_number: 1 }),
    ...Object.fromEntries(
      regions[family].map(([key, heading]) => [
        key,
        { heading, latex: "", image_ids: [] },
      ]),
    ),
  };
}
export function structuredDraft(
  family: Family,
  note?: StructuredDetail,
): StructuredDraft {
  const today = new Date();
  const metadata = note?.metadata || {
    title: "",
    date: [
      today.getFullYear(),
      String(today.getMonth() + 1).padStart(2, "0"),
      String(today.getDate()).padStart(2, "0"),
    ].join("-"),
    project: "",
    context: "estudio",
    tags: [],
  };
  const document: StructuredDocument = note?.document || {
    schema_version: 1,
    template_id:
      family === "cornell"
        ? "historical_cornell_math_letter_v1"
        : "cpi_landscape_letter_v1",
    pages: [emptyPage(family)],
    attribution: {
      enabled: false,
      mode: "auto",
      text: "",
      author: "",
      course: "",
      year: "",
      position: "bottom_right",
    },
    watermark: {
      enabled: false,
      type: "text",
      text: "",
      image_id: "",
      opacity: 0.05,
      scale: 0.4,
      position: "center",
      all_pages: true,
    },
  };
  return {
    metadata: JSON.stringify(metadata),
    document: JSON.stringify(document),
    original: JSON.stringify({ metadata, document }),
    revision: note?.revision || "",
    snapshots: "{}",
    origins: JSON.stringify(
      document.pages.map((p) => (note ? (p.page_id ?? p.page_number) : null)),
    ),
    keys: JSON.stringify(document.pages.map(() => crypto.randomUUID())),
    pending: "",
    request_id: crypto.randomUUID(),
  };
}
export function structuredValues(draft: StructuredDraft, family: Family) {
  const document = JSON.parse(draft.document) as StructuredDocument,
    metadata = JSON.parse(draft.metadata) as Metadata,
    keys = JSON.parse(draft.keys) as string[],
    origins = JSON.parse(draft.origins) as (string | number | null)[],
    snapshots = JSON.parse(draft.snapshots) as Record<string, EditorSnapshot>;
  if (
    !metadata ||
    typeof metadata !== "object" ||
    !document ||
    document.schema_version !== 1 ||
    !Array.isArray(document.pages) ||
    !document.pages.length ||
    document.pages.length > 30 ||
    !Array.isArray(keys) ||
    !Array.isArray(origins) ||
    keys.length !== document.pages.length ||
    origins.length !== keys.length ||
    new Set(keys).size !== keys.length ||
    !snapshots ||
    typeof snapshots !== "object" ||
    Array.isArray(snapshots)
  )
    throw new Error(
      "La estructura del borrador no es válida. Descárgalo antes de reiniciar.",
    );
  for (const page of document.pages)
    for (const [key] of regions[family]) {
      const region = page[key] as Region | undefined;
      if (
        !region ||
        typeof region.latex !== "string" ||
        typeof region.heading !== "string"
      )
        throw new Error(
          "Una región del borrador no se pudo recuperar. Descarga el original.",
        );
    }
  return { document, metadata, keys, origins, snapshots };
}
export function structuredRequest(
  draft: StructuredDraft,
  family: Family,
  saved: boolean,
) {
  const { document, metadata, origins } = structuredValues(draft, family);
  const original = JSON.parse(draft.original) as { metadata: Metadata };
  if (!original?.metadata)
    throw new Error("No se pudo recuperar la revisión original del borrador.");
  return saved
    ? {
        revision: draft.revision,
        document,
        page_origins: origins,
        metadata: Object.fromEntries(
          Object.entries(metadata).filter(
            ([key, value]) =>
              JSON.stringify(value) !==
              JSON.stringify(original.metadata[key as keyof Metadata]),
          ),
        ),
      }
    : { request_id: draft.request_id, metadata, document };
}
export function orderedPages(pages: StructuredPage[], family: Family) {
  return pages.map((page, index) => ({
    ...page,
    [family === "cornell" ? "order" : "page_number"]: index + 1,
  }));
}
