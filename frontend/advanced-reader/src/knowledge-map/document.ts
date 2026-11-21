/** Lossless, bounded LaTeX adapter. Original blocks survive unless edited.
 * Uses the optional {title} environment contract of Cornell/Diario. HTML is an
 * internal view only; MongoDB and the exporters continue to receive LaTeX.
 */
import type { JSONContent } from "@tiptap/core";
export const resultNames: Record<string, string> = {
  definition: "Definición",
  theorem: "Teorema",
  proposition: "Proposición",
  proof: "Demostración",
  remark: "Observación",
  lemma: "Lema",
  corollary: "Corolario",
  example: "Ejemplo",
};
type Group = { value: string; end: number };
export function group(text: string, start: number): Group | undefined {
  if (text[start] !== "{") return;
  let depth = 1;
  for (let i = start + 1; i < text.length; i++) {
    if (text[i] === "\\") {
      i++;
      continue;
    }
    if (text[i] === "{") depth++;
    if (text[i] === "}") {
      depth--;
      if (depth === 0) return { value: text.slice(start + 1, i), end: i + 1 };
    }
  }
}
function clean(node: JSONContent): unknown {
  const attrs = Object.fromEntries(
    Object.entries(node.attrs ?? {}).filter(
      ([key, value]) =>
        !["raw", "signature"].includes(key) &&
        value !== null &&
        value !== undefined,
    ),
  );
  return {
    type: node.type,
    text: node.text,
    attrs,
    marks: (node.marks ?? [])
      .map((m) => ({ type: m.type }))
      .sort((a, b) => a.type.localeCompare(b.type)),
    content: (node.content ?? []).map(clean),
  };
}
export function normalizedOriginals(node: JSONContent): JSONContent {
  const next = { ...node, content: node.content?.map(normalizedOriginals) };
  if (next.attrs?.raw !== undefined && next.attrs.raw !== null)
    next.attrs = { ...next.attrs, signature: signature(next) };
  return next;
}
export function signature(node: JSONContent): string {
  return JSON.stringify(clean(node));
}
function original(node: JSONContent, raw: string): JSONContent {
  node.attrs = { ...node.attrs, raw, signature: signature(node) };
  return node;
}
const plain = (text: string): JSONContent => ({ type: "text", text });
const opaque = (source: string): JSONContent => ({
  type: "sourceAtom",
  attrs: { source },
});
function closing(text: string, token: string, from: number): number {
  for (let i = from; i < text.length; i++) {
    if (text.startsWith(token, i)) return i;
    if (text[i] === "\\") i++;
  }
  return -1;
}
export function inline(text: string): JSONContent[] {
  const result: JSONContent[] = [];
  let buffer = "";
  const flush = () => {
    if (buffer) result.push(plain(buffer));
    buffer = "";
  };
  for (let i = 0; i < text.length;) {
    const open = text.startsWith("\\[", i)
      ? "\\["
      : text.startsWith("\\(", i)
        ? "\\("
        : text.startsWith("$$", i)
          ? "$$"
          : text[i] === "$"
            ? "$"
            : "";
    if (open) {
      flush();
      const close = open === "\\[" ? "\\]" : open === "\\(" ? "\\)" : open;
      const end = closing(text, close, i + open.length),
        stop = end < 0 ? text.length : end;
      result.push(
        original(
          {
            type: "formula",
            attrs: {
              latex: text.slice(i + open.length, stop),
              display: ["\\[", "$$"].includes(open),
              legacy: true,
            },
          },
          text.slice(i, end < 0 ? stop : end + close.length),
        ),
      );
      i = end < 0 ? stop : end + close.length;
      continue;
    }
    if (text[i] !== "\\") {
      buffer += text[i++];
      continue;
    }
    if ("%$&#_{}".includes(text[i + 1] ?? "\u0000")) {
      buffer += text[i + 1];
      i += 2;
      continue;
    }
    if (text[i + 1] === "\\") {
      flush();
      result.push({ type: "hardBreak" });
      i += 2;
      continue;
    }
    const match = /^\\([A-Za-z]+\*?)/u.exec(text.slice(i));
    if (!match) {
      buffer += text[i++];
      continue;
    }
    const name = match[1],
      arg = group(text, i + match[0].length);
    flush();
    if (arg && ["textbf", "textit", "emph"].includes(name)) {
      const mark = name === "textbf" ? "bold" : "italic";
      result.push(
        ...inline(arg.value).map((n) => ({
          ...n,
          marks: [...(n.marks ?? []), { type: mark }],
        })),
      );
      i = arg.end;
    } else {
      let end = i + match[0].length;
      while (text[end] === "{") {
        const next = group(text, end);
        if (!next) break;
        end = next.end;
      }
      result.push(opaque(text.slice(i, end)));
      i = end;
    }
  }
  flush();
  return result;
}
function environment(
  text: string,
  start: number,
):
  | { name: string; body: string; prefix: string; suffix: string; end: number }
  | undefined {
  const token = /^\\begin\{([^}]+)\}/u.exec(text.slice(start));
  if (!token) return;
  const name = token[1];
  let cursor = start + token[0].length,
    level = 1;
  const title = group(text, cursor);
  if (title && resultNames[name]) cursor = title.end;
  const bodyStart = cursor,
    re = /\\(begin|end)\{([^}]+)\}/gu;
  re.lastIndex = cursor;
  for (let match = re.exec(text); match; match = re.exec(text)) {
    if (match[2] !== name) continue;
    level += match[1] === "begin" ? 1 : -1;
    if (!level)
      return {
        name,
        body: text.slice(bodyStart, match.index),
        prefix: text.slice(start, bodyStart),
        suffix: match[0],
        end: re.lastIndex,
      };
  }
}
export function parseDocument(source: string): JSONContent {
  const blocks: JSONContent[] = [];
  let cursor = 0;
  while (cursor < source.length) {
    const start = cursor;
    while (/\s/u.test(source[cursor] ?? "") && cursor < source.length) cursor++;
    const before = source.slice(start, cursor),
      env = environment(source, cursor);
    if (env) {
      const raw = source.slice(start, env.end);
      if (resultNames[env.name])
        blocks.push(
          original(
            {
              type: "resultBlock",
              attrs: {
                environment: env.name,
                before: before + env.prefix,
                after: env.suffix,
                title:
                  group(env.prefix, env.prefix.indexOf("}") + 1)?.value ?? "",
              },
              content: parseDocument(env.body).content,
            },
            raw,
          ),
        );
      else if (["itemize", "enumerate"].includes(env.name)) {
        const pieces = env.body.split("\\item").slice(1);
        blocks.push(
          original(
            {
              type: env.name === "itemize" ? "bulletList" : "orderedList",
              content: pieces.map((piece) => ({
                type: "listItem",
                content: parseDocument(piece).content,
              })),
            },
            raw,
          ),
        );
      } else if (["verbatim", "lstlisting"].includes(env.name))
        blocks.push(
          original(
            { type: "codeBlock", content: env.body ? [plain(env.body)] : [] },
            raw,
          ),
        );
      else
        blocks.push(
          original(
            {
              type: "sourceBlock",
              attrs: {
                source: raw,
                reason: `Construcción ${env.name} conservada; ver fuente o exportación PDF.`,
              },
            },
            raw,
          ),
        );
      cursor = env.end;
      continue;
    }
    const heading = /^\\(section|subsection|subsubsection)\*?/u.exec(
      source.slice(cursor),
    );
    const arg = heading && group(source, cursor + heading[0].length);
    if (heading && arg) {
      blocks.push(
        original(
          {
            type: "heading",
            attrs: {
              level:
                heading[1] === "section"
                  ? 1
                  : heading[1] === "subsection"
                    ? 2
                    : 3,
            },
            content: inline(arg.value),
          },
          source.slice(start, arg.end),
        ),
      );
      cursor = arg.end;
      continue;
    }
    let end = cursor;
    while (end < source.length) {
      if (end > cursor && source.startsWith("\\begin{", end)) break;
      if (source.startsWith("\n\n", end)) {
        end += 2;
        break;
      }
      const open = source.startsWith("\\[", end)
        ? "\\["
        : source.startsWith("\\(", end)
          ? "\\("
          : source.startsWith("$$", end)
            ? "$$"
            : source[end] === "$"
              ? "$"
              : "";
      if (open) {
        const close = open === "\\[" ? "\\]" : open === "\\(" ? "\\)" : open;
        const finish = closing(source, close, end + open.length);
        end = finish < 0 ? source.length : finish + close.length;
      } else {
        if (source[end] === "\\") end++;
        end++;
      }
    }
    if (end <= cursor) end = source.length;
    blocks.push(
      original(
        { type: "paragraph", content: inline(source.slice(cursor, end)) },
        source.slice(start, end),
      ),
    );
    cursor = end;
  }
  return {
    type: "doc",
    content: blocks.length ? blocks : [original({ type: "paragraph" }, "")],
  };
}
export function escapeText(text: string): string {
  return text.replace(
    /[\\%$&#_{}~^]/gu,
    (char) =>
      ({
        "\\": "\\textbackslash{}",
        "~": "\\textasciitilde{}",
        "^": "\\textasciicircum{}",
      })[char] ?? "\\" + char,
  );
}
export function serialize(node: JSONContent): string {
  if (
    node.attrs?.raw !== undefined &&
    node.attrs?.raw !== null &&
    node.attrs.signature === signature(node)
  )
    return String(node.attrs.raw);
  if (node.type === "text") {
    let text = escapeText(node.text ?? "");
    for (const mark of node.marks ?? []) {
      if (mark.type === "bold") text = "\\textbf{" + text + "}";
      if (mark.type === "italic") text = "\\emph{" + text + "}";
    }
    return text;
  }
  const body = (node.content ?? []).map(serialize).join("");
  switch (node.type) {
    case "doc":
      return body;
    case "formula":
      return node.attrs?.display
        ? "\\[" + String(node.attrs.latex) + "\\]"
        : "$" + String(node.attrs?.latex ?? "") + "$";
    case "sourceBlock":
    case "sourceAtom":
      return String(node.attrs?.source ?? "");
    case "resultBlock":
      return (
        String(
          node.attrs?.before ??
            "\\begin{" + String(node.attrs?.environment ?? "remark") + "}\n",
        ) +
        body +
        String(
          node.attrs?.after ??
            "\n\\end{" + String(node.attrs?.environment ?? "remark") + "}",
        )
      );
    case "heading":
      return (
        "\\" +
        (node.attrs?.level === 1 ? "section" : "subsection") +
        "{" +
        body +
        "}\n"
      );
    case "bulletList":
      return "\\begin{itemize}\n" + body + "\\end{itemize}\n";
    case "orderedList":
      return "\\begin{enumerate}\n" + body + "\\end{enumerate}\n";
    case "listItem":
      return "\\item " + body;
    case "codeBlock":
      return (
        "\\begin{verbatim}\n" +
        (node.content ?? []).map((n) => n.text ?? "").join("") +
        "\n\\end{verbatim}\n"
      );
    case "hardBreak":
      return "\\\\\n";
    default:
      return body + "\n\n";
  }
}
