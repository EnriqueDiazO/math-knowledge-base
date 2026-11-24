/** Preserve the reviewed provider payload together with manual fields in one draft. */
export type ReferenceData = {
  reference_id?: string;
  reference_type?: string;
  title?: string;
  authors?: { literal?: string; family?: string; given?: string; orcid?: string }[];
  year?: number | null;
  doi?: string | null;
  isbn?: string[];
  url?: string | null;
  accessed_at?: string | null;
  [key: string]: unknown;
};
export type ReferenceDraft = Record<
  | "reference_id"
  | "reference_type"
  | "title"
  | "author"
  | "year"
  | "doi"
  | "isbn"
  | "url"
  | "accessed_at",
  string
> & { proposal_json?: string };

function validAuthor(author: unknown): boolean {
  if (!author || typeof author !== "object" || Array.isArray(author)) return false;
  return ["literal", "family", "given", "orcid"].every((key) => {
    const field = (author as Record<string, unknown>)[key];
    return field == null || typeof field === "string";
  });
}

export function restoredProposal(value: unknown): {
  data: ReferenceData;
  error: string;
} {
  // Pre-existing manual drafts have no proposal field and retain their original key.
  if (value === undefined) return { data: {}, error: "" };
  try {
    if (typeof value !== "string") throw new Error("invalid proposal");
    const data = JSON.parse(value);
    if (!data || typeof data !== "object" || Array.isArray(data))
      throw new Error("invalid proposal");
    if (
      data.authors !== undefined &&
      (!Array.isArray(data.authors) || !data.authors.every(validAuthor))
    )
      throw new Error("invalid authors");
    if (data.accessed_at != null && typeof data.accessed_at !== "string")
      throw new Error("invalid date");
    return { data, error: "" };
  } catch {
    return {
      data: {},
      error:
        "No se pudo recuperar la propuesta bibliográfica completa. El borrador original se conserva; descárgalo o reinicia la ficha conservando una copia.",
    };
  }
}

export function referenceAccessDate(
  day: string,
  original?: string | null,
): string | null {
  if (!day) return null;
  return original?.slice(0, 10) === day ? original : day + "T00:00:00Z";
}
