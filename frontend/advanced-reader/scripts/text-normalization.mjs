/** Trim only ASCII space/tab before the ECMAScript line terminators, in linear time. */
export function stripAsciiLineEnds(source) {
  const parts = [];
  let beginning = 0;
  for (let index = 0; index <= source.length; index += 1) {
    const code = source.charCodeAt(index);
    if (index < source.length && ![10, 13, 0x2028, 0x2029].includes(code)) continue;
    let end = index;
    while (end > beginning && [9, 32].includes(source.charCodeAt(end - 1))) end -= 1;
    parts.push(source.slice(beginning, end));
    if (index < source.length) parts.push(source[index]);
    beginning = index + 1;
  }
  return parts.join("");
}

/** Preserve the redistributed license text and enforce exactly one final LF. */
export function normalizeRedistributedLicense(source) {
  const text = stripAsciiLineEnds(source.replaceAll("\r\n", "\n"));
  let end = text.length;
  while (end > 0 && text[end - 1] === "\n") end -= 1;
  return text.slice(0, end) + "\n";
}
