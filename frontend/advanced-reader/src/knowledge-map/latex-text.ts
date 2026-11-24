/** Bounded textual commands only. Math and unknown macros remain in their own nodes. */
import type { JSONContent } from "@tiptap/core";
import { documentLink } from "../security/document-links";
type Group = { value: string; end: number };
type ReadGroup = (text: string, start: number) => Group | undefined;
const accents: Record<string, string> = {
  "'": "\u0301",
  "`": "\u0300",
  '"': "\u0308",
  "^": "\u0302",
  "~": "\u0303",
  "=": "\u0304",
  ".": "\u0307",
  c: "\u0327",
  v: "\u030c",
  u: "\u0306",
  H: "\u030b",
  r: "\u030a",
  k: "\u0328",
  b: "\u0331",
};
export function legacyTextCommand(
  text: string,
  start: number,
  group: ReadGroup,
  inline: (text: string) => JSONContent[],
): { nodes: JSONContent[]; end: number } | undefined {
  const token = /^\\([A-Za-z]+|[^A-Za-z\s])/u.exec(text.slice(start));
  if (!token) return;
  const name = token[1];
  let cursor = start + token[0].length;
  while (/\s/u.test(text[cursor] ?? "") && cursor < text.length) cursor++;
  const arg = group(text, cursor);
  if (accents[name]) {
    const base = arg?.value ?? text[cursor];
    if (!base || !/^\p{L}$/u.test(base)) return;
    return {
      nodes: [{ type: "text", text: (base + accents[name]).normalize("NFC") }],
      end: arg?.end ?? cursor + base.length,
    };
  }
  if (arg && ["textbf", "textit", "emph"].includes(name)) {
    const type = name === "textbf" ? "bold" : "italic";
    return {
      nodes: inline(arg.value).map((node) => ({
        ...node,
        marks: [...(node.marks ?? []), { type }],
      })),
      end: arg.end,
    };
  }
  if (!arg || !["href", "url"].includes(name)) return;
  const href = documentLink(arg.value.replace(/\\([%#_&{}])/gu, "$1"));
  if (!href) return;
  const label = name === "href" ? group(text, arg.end) : arg;
  if (!label) return;
  return {
    nodes: (name === "href"
      ? inline(label.value)
      : [{ type: "text", text: href }]
    ).map((node) => ({
      ...node,
      marks: [...(node.marks ?? []), { type: "academicLink", attrs: { href } }],
    })),
    end: label.end,
  };
}
export function latexLink(href: string, label: string): string {
  const safe = documentLink(href);
  return safe
    ? "\\href{" +
        safe.replace(/[%#{}]/gu, (char) => "\\" + char) +
        "}{" +
        label +
        "}"
    : label;
}
