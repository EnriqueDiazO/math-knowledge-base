import { describe, expect, it } from "vitest";
import {
  group,
  inline,
  normalizedOriginals,
  parseDocument,
  serialize,
} from "../src/knowledge-map/document";
import type { JSONContent } from "@tiptap/core";
const fixture = String.raw`\begin{definition}{Slowly oscillating shift}
Let $\Gamma=\overline{\Gamma}\setminus\{0,\infty\}$ and $\alpha:\Gamma\to\Gamma$.
\[
\frac{1}{2}+\begin{pmatrix}1&0\\0&1\end{pmatrix}
\]
\begin{remark}{Interpretation}
Keep \textbf{every \emph{word}} and \cite{author2026}.
\end{remark}
\end{definition}

\begin{tikzpicture}
\draw (0,0)--(1,1);
\end{tikzpicture}
\begin{verbatim}
print("code, not math")
\end{verbatim}
`;
function paragraphs(doc: JSONContent): JSONContent[] {
  return [doc, ...(doc.content ?? []).flatMap(paragraphs)];
}
describe("canonical document compatibility", () => {
  it("preserves real note environments and changes only the editable content of a mixed document",()=>{
    const raw=String.raw`\begin{context}
\begin{definition}{Idea}
Contenido visual $x$.
\end{definition}
\begin{tikzpicture}\draw (0,0)--(1,1);\end{tikzpicture}
\end{context}
`;
    const doc=parseDocument(raw);expect(serialize(doc)).toBe(raw);
    const nodes=paragraphs(doc);expect(nodes.some(n=>n.type==='semanticBlock')).toBe(true);
    const text=nodes.find(n=>n.type==='text'&&n.text?.includes('Contenido visual'))!;text.text='Contenido corregido.';
    expect(serialize(doc)).toContain('Contenido corregido.');
    expect(serialize(doc)).toContain(String.raw`\begin{tikzpicture}\draw (0,0)--(1,1);\end{tikzpicture}`);
  });
  it.each([
    "",
    "Prosa normal con acentos y $x^2$.\n\nSegundo párrafo.",
    fixture,
    "\n\n  \\miMacro{original}{intacto}\n",
    String.raw`\begin{itemize}\item Uno\item Dos\end{itemize}`,
    String.raw`\section{Título}Texto con \textbf{énfasis}.`,
  ])("round trips unmodified bytes: %j", (source) => {
    expect(serialize(parseDocument(source))).toBe(source);
  });
  it("changes only an edited paragraph, preserving macros and adjacent original blocks", () => {
    const raw = "Primer párrafo.\n\n" + fixture,
      doc = parseDocument(raw);
    doc.content![0].content = [{ type: "text", text: "Texto corregido." }];
    const output = serialize(doc);
    expect(output).toBe("Texto corregido.\n\n" + fixture);
    expect(output).toContain("\\draw (0,0)--(1,1);");
  });
  it("separates result blocks, math, code and unknown source without interpreting HTML", () => {
    const doc = parseDocument(fixture),
      nodes = paragraphs(doc);
    expect(
      nodes
        .filter((n) => n.type === "resultBlock")
        .map((n) => n.attrs?.environment),
    ).toEqual(["definition", "remark"]);
    expect(nodes.find((n) => n.type === "resultBlock")?.attrs?.title).toBe(
      "Slowly oscillating shift",
    );
    expect(
      nodes.some(
        (n) =>
          n.type === "sourceBlock" &&
          String(n.attrs?.source).includes("tikzpicture"),
      ),
    ).toBe(true);
    expect(
      nodes.find((n) => n.type === "codeBlock")?.content?.[0].text,
    ).toContain("print(");
    expect(nodes.filter((n) => n.type === "formula").length).toBe(3);
    expect(inline("<img src=x onerror=bad()>")[0]).toEqual({
      type: "text",
      text: "<img src=x onerror=bad()>",
    });
  });
  it("preserves incomplete formulas and balanced groups in recoverable drafts", () => {
    const doc = parseDocument("Antes $\\frac{1}{ y después");
    expect(serialize(doc)).toBe("Antes $\\frac{1}{ y después");
    expect(group("{x{y}z}", 0)).toEqual({ value: "x{y}z", end: 7 });
    expect(group("{sin cierre", 0)).toBeUndefined();
  });
  it("serializes new visual structures as LaTeX without wrapping twice", () => {
    const doc: JSONContent = {
      type: "doc",
      content: [
        {
          type: "resultBlock",
          attrs: { environment: "definition" },
          content: [
            {
              type: "paragraph",
              content: [
                { type: "text", text: "Una definición con " },
                {
                  type: "formula",
                  attrs: { latex: "\\frac{1}{2}", display: false },
                },
                { type: "text", text: " y " },
                {
                  type: "formula",
                  attrs: {
                    latex: "\\begin{pmatrix}1&0\\\\0&1\\end{pmatrix}",
                    display: true,
                  },
                },
              ],
            },
          ],
        },
      ],
    };
    const text = serialize(doc);
    expect(text.match(/\\begin\{definition\}/gu)).toHaveLength(1);
    expect(text).toContain("$\\frac{1}{2}$");
    expect(text).toContain("\\[\\begin{pmatrix}");
  });
  it("retains source after schema normalization and escapes new prose", () => {
    const doc = parseDocument("Texto original $x$");
    const canonical = normalizedOriginals(doc);
    expect(serialize(canonical)).toBe("Texto original $x$");
    expect(
      serialize({
        type: "paragraph",
        content: [{ type: "text", text: "50% de a_b & c#" }],
      }),
    ).toBe("50\\% de a\\_b \\& c\\#\n\n");
  });
});

it.each([
  "definition",
  "theorem",
  "lemma",
  "corollary",
  "proposition",
  "example",
  "remark",
])(
  "keeps the first body character out of the required %s title argument",
  (environment) => {
    const text = serialize({
      type: "doc",
      content: [
        {
          type: "resultBlock",
          attrs: { environment },
          content: [
            {
              type: "paragraph",
              content: [{ type: "text", text: "Prosa completa" }],
            },
          ],
        },
      ],
    });
    expect(text).toBe(
      `\\begin{${environment}}{}\nProsa completa\n\n\n\\end{${environment}}`,
    );
  },
);
it("keeps proof's separate no-title-argument contract and legacy bytes", () => {
  const text = serialize({
    type: "resultBlock",
    attrs: { environment: "proof" },
    content: [
      {
        type: "paragraph",
        content: [{ type: "text", text: "Demostración íntegra" }],
      },
    ],
  });
  expect(text).toContain("\\begin{proof}\nDemostración íntegra");
  const old = "\\begin{definition}Texto legado\\end{definition}";
  expect(serialize(parseDocument(old))).toBe(old);
});
