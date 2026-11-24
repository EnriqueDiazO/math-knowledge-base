/** Trusted local CSS in a component root; keep style-src-elem 'self' unchanged. */
import styles from "./source-editor.css?inline";
const sheets = new WeakMap<Document, CSSStyleSheet>();
export function codeViewport(host: HTMLElement) {
  const document = host.ownerDocument;
  const Sheet = document.defaultView?.CSSStyleSheet;
  if (!Sheet?.prototype.replaceSync)
    throw new Error("Constructable stylesheets unavailable");
  let sheet = sheets.get(document);
  if (!sheet) {
    sheet = new Sheet();
    sheet.replaceSync(
      styles +
        "\n:host{display:block}.code-root{height:100%;border:0;border-radius:0}",
    );
    sheets.set(document, sheet);
  }
  const root = host.attachShadow({ mode: "open" });
  root.adoptedStyleSheets = [sheet];
  const parent = document.createElement("div");
  parent.className = "latex-source code-root";
  root.append(parent);
  return { parent, root };
}
