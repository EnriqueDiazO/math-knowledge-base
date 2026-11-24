/** A damaged local selection must never broaden the set of references imported. */
export function bibtexSelection(raw: string): number[] | undefined {
  try {
    const values: unknown = JSON.parse(raw);
    return Array.isArray(values) &&
      values.every((value) => Number.isSafeInteger(value) && value >= 0)
      ? values
      : undefined;
  } catch {
    return undefined;
  }
}
