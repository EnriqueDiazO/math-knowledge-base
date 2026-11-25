/** Load the code tools only on request; delayed imports cannot revive a closed editor. */
import type { LatexSourceEditor, SourceSelection } from "./source-editor";
import "./source-editor.css";
type Module = { LatexSourceEditor: typeof LatexSourceEditor };
export class LatexSourceLoader {
  private editor?: LatexSourceEditor;
  private pending?: Promise<void>;
  private closed = false;
  private wantsFocus = false;
  private selection?: SourceSelection;
  constructor(
    readonly host: HTMLElement,
    private text: string,
    private changed: () => void,
    private load: () => Promise<Module> = () => import("./source-editor"),
  ) {
    host.className = "latex-source";
  }
  get value() {
    return this.editor?.value ?? this.text;
  }
  set value(value: string) {
    this.text = value;
    if (this.editor) this.editor.value = value;
  }
  snapshot(): SourceSelection {
    return (
      this.editor?.snapshot() ??
      this.selection ?? { anchor: 0, head: 0, scrollTop: 0, scrollLeft: 0 }
    );
  }
  restore(selection: SourceSelection) {
    this.selection = structuredClone(selection);
    this.editor?.restore(selection);
  }
  insert(value: string) {
    const selection = this.snapshot();
    const from = Math.min(selection.anchor, selection.head),
      to = Math.max(selection.anchor, selection.head);
    if (this.editor) {
      this.editor.view.dispatch({
        changes: { from, to, insert: value },
        selection: { anchor: from + value.length },
        scrollIntoView: true,
      });
    } else {
      this.text = this.text.slice(0, from) + value + this.text.slice(to);
      this.selection = {
        ...selection,
        anchor: from + value.length,
        head: from + value.length,
      };
      this.changed();
    }
    this.focus();
  }
  focus(takeFocus = true) {
    if (this.closed) return;
    this.wantsFocus = takeFocus;
    if (this.editor) {
      if (takeFocus) this.editor.focus();
      return;
    }
    if (!this.pending) {
      this.host.textContent = "Abriendo las herramientas de código…";
      this.pending = this.load()
        .then(({ LatexSourceEditor }) => {
          if (this.closed) return;
          this.host.replaceChildren();
          this.editor = new LatexSourceEditor(
            this.host,
            this.text,
            this.changed,
          );
          if (this.selection) this.editor.restore(this.selection);
          if (!this.host.hidden && this.wantsFocus) this.editor.focus();
        })
        .catch(() => {
          if (this.closed) return;
          const message = document.createElement("p");
          message.setAttribute("role", "alert");
          message.textContent =
            "No pudimos abrir las herramientas de código. La fuente permanece intacta y puedes copiarla desde el área de sólo lectura o reintentar.";
          const source = document.createElement("textarea");
          source.readOnly = true;
          source.value = this.text;
          source.setAttribute(
            "aria-label",
            "Fuente LaTeX conservada, sólo lectura",
          );
          const retry = document.createElement("button");
          retry.type = "button";
          retry.textContent = "Reintentar herramientas de código";
          retry.onclick = () => this.focus();
          this.host.replaceChildren(message, source, retry);
        })
        .finally(() => {
          this.pending = undefined;
        });
    }
  }
  destroy() {
    this.closed = true;
    this.editor?.destroy();
    this.host.replaceChildren();
  }
}
