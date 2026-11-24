import { describe, expect, it } from "vitest";
import {
  inline,
  parseDocument,
  serialize,
  signature,
} from "../src/knowledge-map/document";
import type { JSONContent } from "@tiptap/core";
const all = (node: JSONContent): JSONContent[] => [
  node,
  ...(node.content ?? []).flatMap(all),
];
describe("bounded legacy text", () => {
  it("reads the demonstrated John McCarthy accents and links without rewriting their source", () => {
    const raw = String.raw`\begin{remark}{John McCarthy}
Acu\~n\'o el t\'ermino \textit{artificial intelligence}
(\href{https://doi.org/10.1145/367177.367199}{McCarthy, 1960}).
\end{remark}
`;
    const doc = parseDocument(raw),
      nodes = all(doc),
      text = nodes.map((n) => n.text || "").join("");
    expect(text).toContain("Acuñó el término");
    expect(text).toContain("McCarthy, 1960");
    expect(
      nodes.find((n) => n.text?.includes("McCarthy, 1960"))?.marks,
    ).toContainEqual({
      type: "academicLink",
      attrs: { href: "https://doi.org/10.1145/367177.367199" },
    });
    expect(serialize(doc)).toBe(raw);
  });
  it.each([
    String.raw`\'{a}`,
    String.raw`\'a`,
    String.raw`\~{n}`,
    String.raw`\"{u}`,
  ])("preserves unedited accent spelling: %s", (source) =>
    expect(serialize(parseDocument(source))).toBe(source),
  );
  it("keeps mathematics and unknown commands protected while refusing unsafe links", () => {
    const source = String.raw`$\hat x+\tilde y$ \href{javascript:alert(1)}{peligro} \unknown{intacto}`;
    const nodes = all(parseDocument(source));
    expect(nodes.filter((n) => n.type === "formula")[0].attrs?.latex).toBe(
      String.raw`\hat x+\tilde y`,
    );
    expect(
      nodes.some((n) => n.marks?.some((m) => m.type === "academicLink")),
    ).toBe(false);
    expect(serialize(parseDocument(source))).toBe(source);
  });
  it("serializes edited links safely and includes their destination in provenance signatures", () => {
    const a: JSONContent = {
      type: "text",
      text: "Un enlace",
      marks: [
        {
          type: "academicLink",
          attrs: { href: "https://example.org/a?q=1&b=2" },
        },
      ],
    };
    const b = {
      ...a,
      marks: [
        { type: "academicLink", attrs: { href: "https://example.org/other" } },
      ],
    };
    expect(signature(a)).not.toBe(signature(b));
    expect(serialize(a)).toBe(
      String.raw`\href{https://example.org/a?q=1&b=2}{Un enlace}`,
    );
    expect(
      inline(String.raw`\url{https://example.org/paper}`)[0].marks?.[0].type,
    ).toBe("academicLink");
  });
});
