export const MAX_SEARCH_QUERY_CODE_POINTS = 256;

export function limitSearchQuery(value: string): string {
  return Array.from(value).slice(0, MAX_SEARCH_QUERY_CODE_POINTS).join("");
}

export function normalizeSearchQuery(value: string): string {
  return limitSearchQuery(value.replace(/\s+/gu, " ").trim());
}
