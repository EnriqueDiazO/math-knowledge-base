/** Protected advanced LaTeX: source is editable explicitly, never interpreted as HTML. */
import { Node, type Editor } from "@tiptap/core";
export type PreviewFigure = (source: string, host: HTMLElement) => void;
export function editProtectedSource(
  editor: Editor,
  host: HTMLElement,
  position?: number,
) {
  const before =
    position === undefined ? undefined : editor.state.doc.nodeAt(position);
  const dialog = document.createElement("dialog");
  dialog.className = "source-block-dialog";
  const heading = document.createElement("h2");
  heading.textContent = "Bloque LaTeX avanzado";
  const label = document.createElement("label");
  label.textContent = "Código LaTeX protegido";
  const input = document.createElement("textarea");
  input.value = String(before?.attrs.source ?? "");
  input.maxLength = 200000;
  label.append(input);
  const explanation = document.createElement("p");
  explanation.textContent =
    "El código se conserva literalmente para la exportación. Las macros y entornos deben estar definidos en las plantillas o en tus macros del documento.";
  const message = document.createElement("p");
  message.setAttribute("role", "alert");
  const confirm = document.createElement("button");
  confirm.type = "button";
  confirm.textContent = "Conservar bloque";
  const cancel = document.createElement("button");
  cancel.type = "button";
  cancel.textContent = "Cancelar";
  const dispose = () => dialog.remove();
  editor.on("destroy", dispose);
  const close = () => {
    dialog.close();
    dialog.remove();
    editor.off("destroy", dispose);
    if (!editor.isDestroyed) editor.view.focus();
  };
  cancel.onclick = close;
  dialog.addEventListener("cancel", (event) => {
    event.preventDefault();
    close();
  });
  confirm.onclick = () => {
    if (!input.value.trim() || input.value.includes("\0")) {
      message.textContent =
        "Escribe el fragmento LaTeX. El documento no cambió.";
      return;
    }
    if (position !== undefined) {
      const current = editor.state.doc.nodeAt(position);
      if (
        !current ||
        current.type.name !== "sourceBlock" ||
        current.attrs.source !== before?.attrs.source
      ) {
        message.textContent =
          "El bloque cambió. Copia tu texto antes de volver a abrirlo.";
        return;
      }
      editor.view.dispatch(
        editor.state.tr.setNodeMarkup(position, undefined, {
          ...current.attrs,
          source: input.value,
        }),
      );
    } else
      editor
        .chain()
        .focus()
        .insertContent({
          type: "sourceBlock",
          attrs: { source: input.value, reason: "LaTeX avanzado protegido" },
        })
        .run();
    close();
  };
  dialog.append(heading, explanation, label, message, confirm, cancel);
  host.append(dialog);
  dialog.showModal();
  input.focus();
}
export const SourceBlock = Node.create({
  name: "sourceBlock",
  group: "block",
  atom: true,
  addOptions() {
    return { onPreview: undefined as PreviewFigure | undefined };
  },
  addAttributes() {
    return {
      source: { default: "" },
      reason: { default: "Fragmento original protegido" },
    };
  },
  parseHTML() {
    return [{ tag: "details[data-source-block]" }];
  },
  renderHTML({ node }) {
    return [
      "details",
      { "data-source-block": "", class: "protected-block" },
      ["summary", {}, String(node.attrs.reason)],
      ["pre", {}, ["code", {}, String(node.attrs.source)]],
    ];
  },
  addNodeView() {
    return ({ node, editor, getPos }) => {
      const details = document.createElement("details");
      details.dataset.sourceBlock = "";
      details.className = "protected-block";
      const summary = document.createElement("summary");
      summary.textContent = String(node.attrs.reason);
      const pre = document.createElement("pre"),
        code = document.createElement("code");
      code.textContent = String(node.attrs.source);
      pre.append(code);
      details.append(summary, pre);
      const preview = this.options.onPreview;
      if (
        preview &&
        String(node.attrs.source).includes("\\begin{tikzpicture}")
      ) {
        const show = document.createElement("button");
        show.type = "button";
        show.textContent = "Ver figura";
        show.onclick = () => preview(String(node.attrs.source), details);
        details.append(show);
      }
      if (editor.isEditable) {
        const edit = document.createElement("button");
        edit.type = "button";
        edit.textContent = "Editar bloque LaTeX";
        edit.onclick = () => {
          const pos = getPos();
          if (typeof pos === "number")
            editProtectedSource(editor, document.body, pos);
        };
        details.append(edit);
      }
      return { dom: details };
    };
  },
});
