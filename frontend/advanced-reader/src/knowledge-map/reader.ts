import type { Node } from "./model";
import { renderDocument } from "./document-editor";
/** Read one immutable snapshot. Replacing a reader destroys its previous tree. */
export function openReader(
  parent: HTMLElement,
  node: Node,
  size: number,
  closed: () => void,
  provenance?: (parent: HTMLElement) => void,
): () => void {
  const dialog = document.createElement("dialog");
  dialog.className = "document-dialog reader-dialog";
  const top = document.createElement("header");
  const title = document.createElement("h2");
  title.textContent = node.titulo;
  const close = document.createElement("button");
  close.type = "button";
  close.textContent = "Cerrar lectura";
  top.append(title, close);
  const label = document.createElement("label");
  label.textContent = "Tamaño de lectura";
  const range = document.createElement("input");
  range.type = "range";
  range.min = "16";
  range.max = "26";
  range.value = String(size);
  range.setAttribute("aria-label", "Tamaño de lectura");
  label.append(range);
  top.append(label);
  const article = document.createElement("article");
  article.className = "reading-document";
  article.style.fontSize = size + "px";
  range.oninput = () => (article.style.fontSize = range.value + "px");
  const type = document.createElement("p");
  type.textContent = node.tipo;
  type.className = "document-kind";
  article.append(type);
  const body = document.createElement("div");
  article.append(body);
  const dispose = renderDocument(body, node.contenido_latex);
  const references = document.createElement("section");
  references.append(
    Object.assign(document.createElement("h3"), {
      textContent: "Referencia y procedencia",
    }),
  );
  references.append(
    Object.assign(document.createElement("p"), { textContent: node.source }),
  );
  Object.entries(node.referencia ?? {}).forEach(([name, value]) =>
    references.append(
      Object.assign(document.createElement("p"), {
        textContent: `${name}: ${value}`,
      }),
    ),
  );
  const details = document.createElement("details");
  details.append(
    Object.assign(document.createElement("summary"), {
      textContent: "Identidad y fuente original",
    }),
    Object.assign(document.createElement("p"), { textContent: node.key }),
    Object.assign(document.createElement("pre"), {
      textContent: node.contenido_latex,
    }),
  );
  references.append(details);
  article.append(references);
  provenance?.(article);
  dialog.append(top, article);
  parent.append(dialog);
  dialog.showModal();
  let disposed = false;
  const cleanup = () => {
    if (disposed) return;
    disposed = true;
    dispose();
    dialog.remove();
    closed();
  };
  close.onclick = () => dialog.close();
  dialog.onclose = cleanup;
  return cleanup;
}
