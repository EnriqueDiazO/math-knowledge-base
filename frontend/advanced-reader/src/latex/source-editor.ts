import { tags } from "@lezer/highlight";
/** Full source editor: canonical strings in/out; no rewriting, rendering or persistence. */
import { EditorState } from "@codemirror/state";
import {
  EditorView,
  keymap,
  lineNumbers,
  drawSelection,
  highlightActiveLine,
  highlightActiveLineGutter,
} from "@codemirror/view";
import {
  defaultKeymap,
  history,
  historyKeymap,
  indentWithTab,
  undo,
  redo,
  undoDepth,
  redoDepth,
} from "@codemirror/commands";
import { search, searchKeymap, openSearchPanel } from "@codemirror/search";
import {
  autocompletion,
  completionKeymap,
  snippet,
} from "@codemirror/autocomplete";
import {
  StreamLanguage,
  syntaxHighlighting,
  HighlightStyle,
  bracketMatching,
  indentOnInput,
} from "@codemirror/language";
import { stex } from "@codemirror/legacy-modes/mode/stex";
import { latexCompletion, latexSnippets } from "./completions";
import "./source-editor.css";
import { codeViewport } from "./source-styles";

export type SourceSelection = {
  anchor: number;
  head: number;
  scrollTop: number;
  scrollLeft: number;
  height?: string;
};
const phrases = {
  Find: "Buscar",
  Replace: "Reemplazar",
  next: "siguiente",
  previous: "anterior",
  all: "todos",
  "match case": "mayúsculas",
  "by word": "palabra completa",
  regexp: "expresión regular",
  replace: "reemplazar",
  "replace all": "reemplazar todos",
  close: "cerrar",
  Search: "Buscar",
  "No results": "Sin resultados",
  "No matches found": "Sin coincidencias",
  "Search for": "Buscar texto",
  "Replace with": "Reemplazar por",
  "Fold line": "Plegar línea",
  "Unfold line": "Desplegar línea",
};
const node = <K extends keyof HTMLElementTagNameMap>(tag: K, text = "") => {
  const value = document.createElement(tag);
  value.textContent = text;
  return value;
};

const sourceHighlight = syntaxHighlighting(
  HighlightStyle.define([
    {
      tag: [tags.keyword, tags.name],
      color: "var(--mm-code-command)",
    },
    {
      tag: tags.comment,
      color: "var(--mm-code-comment)",
      fontStyle: "italic",
    },
    {
      tag: [tags.string, tags.number],
      color: "var(--mm-code-value)",
    },
    {
      tag: [tags.bracket, tags.punctuation],
      color: "var(--mm-text)",
    },
  ]),
);
const sourceTheme = EditorView.theme(
  {
    "&": {
      height: "100%",
      color: "var(--mm-text)",
      backgroundColor: "var(--mm-panel)",
    },
    ".cm-scroller": {
      overflow: "auto",
      fontFamily: "ui-monospace, monospace",
      lineHeight: "1.6",
    },
  },
  { dark: true },
);
const sourceLanguage = StreamLanguage.define(stex);

export class LatexSourceEditor {
  readonly view: EditorView;
  private readonly height: HTMLSelectElement;
  constructor(
    readonly host: HTMLElement,
    source: string,
    changed: () => void,
    restored?: SourceSelection,
  ) {
    host.className = "latex-source";
    const tools = node("div");
    tools.className = "latex-source-tools";
    tools.setAttribute("role", "group");
    tools.setAttribute("aria-label", "Herramientas de código LaTeX");
    const button = (label: string, action: () => void) => {
      const value = node("button", label);
      value.type = "button";
      value.onclick = action;
      tools.append(value);
      return value;
    };
    button("Buscar y reemplazar", () => openSearchPanel(this.view));
    const backward = button("Deshacer código", () => {
      undo(this.view);
      this.view.focus();
    });
    const forward = button("Rehacer código", () => {
      redo(this.view);
      this.view.focus();
    });
    const fragments = node("select");
    fragments.setAttribute("aria-label", "Insertar fragmento LaTeX");
    fragments.append(new Option("Insertar entorno…", ""));
    latexSnippets.forEach(({ name, label }) =>
      fragments.append(new Option(label, name)),
    );
    fragments.onchange = () => {
      const item = latexSnippets.find(({ name }) => name === fragments.value);
      if (item) {
        const selection = this.view.state.selection.main;
        snippet(item.template)(this.view, null, selection.from, selection.to);
        this.view.focus();
      }
      fragments.value = "";
    };
    tools.append(fragments);
    const lineLabel = node("label", "Ir a línea"),
      line = node("input");
    line.type = "number";
    line.min = "1";
    line.value = "1";
    line.inputMode = "numeric";
    lineLabel.append(line);
    tools.append(lineLabel);
    const status = node("span");
    status.setAttribute("role", "status");
    button("Ir", () => {
      const index = Number(line.value);
      if (
        !Number.isInteger(index) ||
        index < 1 ||
        index > this.view.state.doc.lines
      ) {
        status.textContent = `Elige una línea entre 1 y ${this.view.state.doc.lines}.`;
        return;
      }
      const position = this.view.state.doc.line(index).from;
      this.view.dispatch({
        selection: { anchor: position },
        effects: EditorView.scrollIntoView(position, { y: "center" }),
      });
      this.view.focus();
      status.textContent = "";
    });
    tools.append(status);
    const parent = node("div");
    parent.className = "latex-source-viewport";
    this.height = node("select");
    this.height.setAttribute("aria-label", "Altura del código");
    this.height.append(
      new Option("Altura normal", "28rem"),
      new Option("Compacto", "20rem"),
      new Option("Amplio", "48rem"),
    );
    this.height.onchange = () => {
      parent.style.height = this.height.value;
      this.view.requestMeasure();
      changed();
    };
    tools.append(this.height);
    const hint = node(
      "p",
      "Ctrl+F: buscar · Ctrl+H: reemplazar · Ctrl+Espacio: completar · Tab: siguiente campo del fragmento · Esc y Tab: salir del editor.",
    );
    hint.className = "latex-source-hint";
    host.append(tools, parent, hint);
    const code = codeViewport(parent);
    this.view = new EditorView({
      parent: code.parent,
      root: code.root,
      state: EditorState.create({
        doc: source,
        extensions: [
          // Only LF splits lines. CRs remain literal, preserving mixed/CRLF source exactly.
          EditorState.lineSeparator.of("\n"),
          EditorState.phrases.of(phrases),
          lineNumbers(),
          drawSelection(),
          highlightActiveLine(),
          highlightActiveLineGutter(),
          history(),
          indentOnInput(),
          bracketMatching(),
          sourceLanguage,
          sourceHighlight,
          search({ top: true }),
          autocompletion({ override: [latexCompletion] }),
          keymap.of([
            ...completionKeymap,
            ...historyKeymap,
            ...searchKeymap,
            ...defaultKeymap,
            indentWithTab,
          ]),
          EditorView.contentAttributes.of({
            "aria-label": "Fuente LaTeX",
            "aria-multiline": "true",
            spellcheck: "false",
          }),
          sourceTheme,
          EditorView.updateListener.of((update) => {
            backward.disabled = undoDepth(update.state) === 0;
            forward.disabled = redoDepth(update.state) === 0;
            if (
              update.docChanged ||
              update.selectionSet ||
              update.viewportChanged
            )
              changed();
          }),
        ],
      }),
    });
    backward.disabled = true;
    forward.disabled = true;
    if (restored) this.restore(restored);
  }
  get value() {
    return this.view.state.sliceDoc();
  }
  set value(source: string) {
    if (source === this.value) return;
    this.view.dispatch({
      changes: { from: 0, to: this.view.state.doc.length, insert: source },
    });
  }
  snapshot(): SourceSelection {
    const { anchor, head } = this.view.state.selection.main;
    return {
      anchor,
      head,
      scrollTop: this.view.scrollDOM.scrollTop,
      scrollLeft: this.view.scrollDOM.scrollLeft,
      height: this.height.value,
    };
  }
  restore(selection: SourceSelection) {
    if (
      selection.height &&
      ["20rem", "28rem", "48rem"].includes(selection.height)
    ) {
      this.height.value = selection.height;
      this.height.onchange?.(new Event("change"));
    }
    const clamp = (position: number) =>
      Number.isFinite(position)
        ? Math.max(0, Math.min(this.view.state.doc.length, position))
        : 0;
    this.view.dispatch({
      selection: {
        anchor: clamp(selection.anchor),
        head: clamp(selection.head),
      },
    });
    this.view.scrollDOM.scrollTop = selection.scrollTop;
    this.view.scrollDOM.scrollLeft = selection.scrollLeft;
  }
  focus() {
    this.view.focus();
  }
  destroy() {
    this.view.destroy();
    this.host.replaceChildren();
  }
}
