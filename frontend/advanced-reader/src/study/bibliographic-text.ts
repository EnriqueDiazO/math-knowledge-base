/** Display existing textual LaTeX through its canonical parser; never rewrite metadata. */
import type { JSONContent } from "@tiptap/core";
import { parseDocument } from "../knowledge-map/document";
export function bibliographicText(value: string | undefined | null): string {
  if (!value) return "";
  function text(node: JSONContent): string {
    if (node.type === "text") return node.text || "";
    if (node.attrs?.source) return String(node.attrs.source);
    if (!node.content && node.attrs?.raw) return String(node.attrs.raw);
    if (node.attrs?.latex) return String(node.attrs.latex);
    return (node.content || []).map(text).join("");
  }
  return parseDocument(value).content?.map(text).join(" ").trim() || value;
}
