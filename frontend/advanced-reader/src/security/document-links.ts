/** Academic links are data, never executable protocols or markup. */
export function documentLink(
  value: string | null | undefined,
): string | undefined {
  if (
    !value ||
    Array.from(value).some((char) => {
      const code = char.codePointAt(0)!;
      return code <= 32 || code === 127;
    })
  )
    return;
  try {
    const url = new URL(value);
    if (
      !["https:", "http:"].includes(url.protocol) ||
      url.username ||
      url.password
    )
      return;
    return url.href;
  } catch {
    return;
  }
}
