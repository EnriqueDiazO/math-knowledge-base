import type { Selection as MathSelection } from "mathlive";
import { Editor, Extension, Node as TiptapNode } from "@tiptap/core";
import type { JSONContent } from "@tiptap/core";
import StarterKit from "@tiptap/starter-kit";
import { TextSelection } from "@tiptap/pm/state";
import { makeMath, mathErrors } from "./math";
import { mountMathKeyboard } from "./keyboard";
import { mountFormulaTools } from "./formula-tools";
import { AcademicLink } from "./document-link";
import { SemanticBlock, studyBlocks } from "./document-blocks";
import { SourceBlock, editProtectedSource } from "./document-source";
import type { PreviewFigure } from "./document-source";
import { conceptKind, conceptType, resultChoices } from "./concept-types";
import "./document-tools.css";
import "./document-base.css";
import type { SourceSelection } from "../latex/source-editor";
import { LatexSourceLoader } from "../latex/source-loader";
import {
  normalizedOriginals,
  parseDocument,
  resultNames,
  serialize,
} from "./document";

const dom = <K extends keyof HTMLElementTagNameMap>(tag: K, text = "") => {
  const element = document.createElement(tag);
  element.textContent = text;
  return element;
};
function control(
  parent: HTMLElement,
  text: string,
  action: () => void,
): HTMLButtonElement {
  const glyphs: Record<string, string> = {
    Negrita: "B",
    Énfasis: "I",
    Encabezado: "H₂",
    Lista: "• ≡",
    "Lista numerada": "1. ≡",
    Código: "</>",
    "Deshacer texto": "↶",
    "Rehacer texto": "↷",
  };
  const button = dom("button", glyphs[text] ?? text);
  if (glyphs[text]) button.setAttribute("aria-label", text);
  button.title = text;
  button.type = "button";
  button.onmousedown = (event) => event.preventDefault();
  button.onclick = action;
  parent.append(button);
  return button;
}
const Provenance = Extension.create({
  name: "originalSource",
  addGlobalAttributes() {
    return [
      {
        types: [
          "paragraph",
          "heading",
          "bulletList",
          "orderedList",
          "listItem",
          "codeBlock",
          "blockquote",
          "resultBlock",
          "semanticBlock",
          "formula",
          "sourceBlock",
        ],
        attributes: {
          raw: { default: null, rendered: false },
          signature: { default: null, rendered: false },
        },
      },
    ];
  },
});
const ResultBlock = TiptapNode.create({
  name: "resultBlock",
  group: "block",
  content: "block+",
  defining: true,
  addAttributes() {
    return {
      environment: { default: "remark" },
      title: { default: "" },
      before: { default: null },
      after: { default: null },
    };
  },
  parseHTML() {
    return [{ tag: "section[data-result]" }];
  },
  renderHTML({ node }) {
    return [
      "section",
      {
        "data-result": String(node.attrs.environment),
        "data-concept-type":
          conceptKind(String(node.attrs.environment)) ?? "proof",
        "aria-label":
          resultNames[String(node.attrs.environment)] ?? "Resultado",
      },
      [
        "header",
        {
          contenteditable: "false",
          "data-type-symbol":
            conceptType(String(node.attrs.environment))?.symbol ?? "",
        },
        `${resultNames[String(node.attrs.environment)] ?? "Resultado"}${node.attrs.title ? ": " + String(node.attrs.title) : ""}`,
      ],
      ["div", 0],
    ];
  },
});
const SourceAtom = TiptapNode.create({
  name: "sourceAtom",
  inline: true,
  group: "inline",
  atom: true,
  addAttributes() {
    return { source: { default: "" } };
  },
  parseHTML() {
    return [{ tag: "span[data-source-atom]" }];
  },
  renderHTML({ node }) {
    return [
      "span",
      {
        "data-source-atom": "",
        class: "protected-inline",
        title: "Fragmento original protegido",
        contenteditable: "false",
      },
      String(node.attrs.source),
    ];
  },
});
const Formula = TiptapNode.create({
  name: "formula",
  inline: true,
  group: "inline",
  atom: true,
  selectable: true,
  addAttributes() {
    return {
      latex: { default: "" },
      display: { default: false },
      legacy: { default: false },
    };
  },
  parseHTML() {
    return [{ tag: "span[data-formula]" }];
  },
  renderHTML({ node }) {
    return [
      "span",
      { "data-formula": "", "data-display": String(node.attrs.display) },
      String(node.attrs.latex),
    ];
  },
  addNodeView() {
    return ({ node, editor, getPos }) => {
      const wrapper = dom("span");
      wrapper.className = node.attrs.display
        ? "formula-block"
        : "formula-inline";
      const errors = mathErrors(String(node.attrs.latex));
      const protectedFormula = Boolean(node.attrs.legacy && errors.length);
      const math = makeMath(
        String(node.attrs.latex),
        editor.isEditable && !protectedFormula,
      );
      const warning = dom("span");
      warning.className = "formula-warning";
      warning.setAttribute("role", "status");
      const report = () => {
        const current = mathErrors(math.value);
        warning.textContent = current.length
          ? protectedFormula
            ? "Fórmula original conservada; ver fuente"
            : "Fórmula en elaboración"
          : "";
        wrapper.dataset.invalid = String(
          current.length > 0 && !protectedFormula,
        );
      };
      const update = () => {
        const pos = getPos();
        if (typeof pos !== "number") return;
        editor.view.dispatch(
          editor.state.tr.setNodeMarkup(pos, undefined, {
            ...node.attrs,
            latex: math.value,
            legacy: false,
          }),
        );
        report();
      };
      math.addEventListener("input", update);
      math.addEventListener("move-out", (event) => {
        const pos = getPos();
        if (typeof pos !== "number") return;
        const direction = (event as CustomEvent).detail?.direction;
        const target = direction === "backward" ? pos : pos + node.nodeSize;
        editor.view.dispatch(
          editor.state.tr.setSelection(
            TextSelection.near(editor.state.doc.resolve(target)),
          ),
        );
        editor.view.focus();
      });
      wrapper.append(math, warning);
      if (protectedFormula) {
        const details = dom("details");
        details.append(
          dom("summary", "Ver fuente"),
          dom("code", String(node.attrs.latex)),
        );
        wrapper.append(details);
      }
      report();
      return {
        dom: wrapper,
        stopEvent: (event) =>
          event.target instanceof globalThis.Node &&
          math.contains(event.target),
        ignoreMutation: () => true,
        update(next) {
          if (next.type !== node.type) return false;
          node = next;
          if (math.value !== String(next.attrs.latex))
            math.setValue(String(next.attrs.latex), {
              silenceNotifications: true,
            });
          report();
          return true;
        },
        destroy() {
          math.removeEventListener("input", update);
        },
      };
    };
  },
});
export const documentExtensions = (preview?: PreviewFigure) => [
  StarterKit.configure({ link: false, underline: false, trailingNode: false }),
  Provenance,
  AcademicLink,
  SemanticBlock,
  ResultBlock,
  Formula,
  SourceAtom,
  SourceBlock.configure({ onPreview: preview }),
];
export type EditorSnapshot = {
  json: JSONContent;
  selection: number;
  scroll: number;
  sourceMode: boolean;
  sourceSelection?: SourceSelection;
  dialogScroll?: number;
  math?: { index: number; selection: MathSelection };
};
export class DocumentEditor {
  readonly editor: Editor;
  private source: LatexSourceLoader;
  private visual: HTMLDivElement;
  private preview: HTMLDivElement;
  private sourceMode = false;
  private activeMath?: ReturnType<typeof makeMath>;
  private restored?: EditorSnapshot;
  private disposeKeyboard: () => void = () => {};
  private disposePreview?: () => void;
  private viewport: HTMLElement | null;
  constructor(
    private parent: HTMLElement,
    latex: string,
    private changed: (latex: string, snapshot: EditorSnapshot) => void,
    snapshot?: EditorSnapshot,
    surface?: {
      keyboardContainer: HTMLElement;
      viewport: HTMLElement;
      preview?: PreviewFigure;
      compiled?: PreviewFigure;
    },
  ) {
    this.restored = snapshot;
    parent.classList.add("document-composer");
    this.viewport = surface?.viewport ?? parent.closest("dialog");
    const keyboardContainer = surface?.keyboardContainer ?? this.viewport;
    if (keyboardContainer)
      this.disposeKeyboard = mountMathKeyboard(keyboardContainer);
    const toolbar = dom("div");
    toolbar.className = "document-toolbar";
    toolbar.setAttribute("aria-label", "Herramientas del documento");
    const toolGroup = (label: string) => {
      const group = dom("div");
      group.className = "document-tool-group";
      group.setAttribute("role", "group");
      group.setAttribute("aria-label", label);
      toolbar.append(group);
      return group;
    };
    let tools = toolGroup("Texto y estructura");
    this.visual = dom("div");
    this.visual.className = "visual-document";
    this.visual.addEventListener("focusin", (event) => {
      const field = event
        .composedPath()
        .find(
          (target) =>
            target instanceof HTMLElement && target.tagName === "MATH-FIELD",
        );
      this.activeMath = field as ReturnType<typeof makeMath> | undefined;
    });
    this.visual.addEventListener(
      "selection-change",
      (event) => {
        const field = event
          .composedPath()
          .find(
            (target) =>
              target instanceof HTMLElement && target.tagName === "MATH-FIELD",
          );
        if (field) this.activeMath = field as ReturnType<typeof makeMath>;
        if (this.editor) this.remember();
      },
      true,
    );
    const sourceHost = dom("section");
    sourceHost.hidden = true;
    this.preview = dom("div");
    this.preview.className = "document-preview";
    this.preview.hidden = true;
    this.editor = new Editor({
      injectCSS: false,
      element: this.visual,
      extensions: documentExtensions(surface?.preview),
      content: snapshot?.json ?? parseDocument(latex),
      editorProps: {
        attributes: {
          role: "textbox",
          "aria-label": "Documento visual",
          "aria-multiline": "true",
        },
      },
      onUpdate: () => this.notify(),
      onSelectionUpdate: () => this.remember(),
    });
    if (!snapshot)
      this.editor.commands.setContent(
        normalizedOriginals(this.editor.getJSON()),
        { emitUpdate: false },
      );
    const format = (name: string, action: () => void) =>
      control(tools, name, action);
    format("Negrita", () => this.editor.chain().focus().toggleBold().run());
    format("Énfasis", () => this.editor.chain().focus().toggleItalic().run());
    format("Encabezado", () =>
      this.editor.chain().focus().toggleHeading({ level: 2 }).run(),
    );
    format("Lista", () => this.editor.chain().focus().toggleBulletList().run());
    format("Lista numerada", () =>
      this.editor.chain().focus().toggleOrderedList().run(),
    );
    format("Código", () => this.editor.chain().focus().toggleCodeBlock().run());
    tools = toolGroup("Historial del texto");
    format("Deshacer texto", () => this.editor.chain().focus().undo().run());
    format("Rehacer texto", () => this.editor.chain().focus().redo().run());
    const results = dom("select");
    results.setAttribute("aria-label", "Insertar bloque de resultado");
    results.append(new Option("Bloque de resultado…", ""));
    resultChoices.forEach((value) =>
      results.append(new Option(resultNames[value], value)),
    );
    results.onchange = () => {
      if (results.value)
        this.editor
          .chain()
          .focus()
          .insertContent({
            type: "resultBlock",
            attrs: { environment: results.value },
            content: [{ type: "paragraph" }],
          })
          .run();
      results.value = "";
    };
    tools = toolGroup("Resultados matemáticos");
    tools.append(results);
    tools = toolGroup("Estructura de estudio");
    const structures = dom("select");
    structures.setAttribute("aria-label", "Insertar bloque de estudio");
    structures.append(new Option("Bloque de estudio…", ""));
    Object.entries(studyBlocks).forEach(([value, block]) =>
      structures.append(new Option(block.label, value)),
    );
    structures.onchange = () => {
      if (structures.value)
        this.editor
          .chain()
          .focus()
          .insertContent({
            type: "semanticBlock",
            attrs: { environment: structures.value },
            content: [{ type: "paragraph" }],
          })
          .run();
      structures.value = "";
    };
    tools.append(structures);
    tools = toolGroup("Fórmulas y plantillas");
    format("Insertar fórmula en línea", () => this.insertFormula(false));
    format("Insertar fórmula en bloque", () => this.insertFormula(true));
    const templates: Record<string, string> = {
      Fracción: "\\frac{#0}{#?}",
      Exponente: "#0^{#?}",
      Subíndice: "#0_{#?}",
      Raíz: "\\sqrt{#0}",
      Integral: "\\int_{0}^{1}#0\\,dx",
      "Matriz 2×2": "\\begin{pmatrix}1&0\\\\0&1\\end{pmatrix}",
      Símbolos: "\\forall x\\in\\mathbb{R}",
    };
    Object.entries(templates).forEach(([name, template]) =>
      format(name, () => this.insertTemplate(template)),
    );
    mountFormulaTools(tools, {
      insert: (template) => this.insertTemplate(template),
      active: () => this.editableMath(),
    });
    format("Volver al párrafo", () => {
      this.visual
        .querySelectorAll("math-field")
        .forEach((field) => (field as unknown as HTMLElement).blur());
      this.editor.commands.setTextSelection(
        this.editor.state.doc.content.size - 1,
      );
      this.editor.commands.insertContent({ type: "paragraph" });
      this.editor.view.focus();
    });
    tools = toolGroup("Representación del documento");
    format("Bloque LaTeX avanzado", () =>
      editProtectedSource(this.editor, document.body),
    );
    format("Fuente LaTeX", () => this.toggleSource());
    format("Vista previa", () => {
      this.preview.hidden = !this.preview.hidden;
      if (!this.preview.hidden) this.updatePreview();
    });
    const compiled = dom("div");
    compiled.className = "document-compiled-preview";
    if (surface?.compiled) {
      const compile = surface.compiled;
      format("Vista compilada", () => compile(this.value(), compiled));
    }
    parent.append(toolbar, this.visual, sourceHost, this.preview, compiled);
    this.source = new LatexSourceLoader(sourceHost, latex, () => {
      if (this.sourceMode) this.notify();
    });
    if (snapshot) {
      this.sourceMode = snapshot.sourceMode;
      this.visual.hidden = this.sourceMode;
      this.source.host.hidden = !this.sourceMode;
      if (snapshot.sourceSelection)
        this.source.restore(snapshot.sourceSelection);
      if (snapshot.math && !this.sourceMode) {
        const math = this.visual.querySelectorAll("math-field")[
          snapshot.math.index
        ] as ReturnType<typeof makeMath> | undefined;
        if (math) {
          this.activeMath = math;
          math.selection = structuredClone(snapshot.math.selection);
        }
      }
      try {
        this.editor.commands.setTextSelection(snapshot.selection);
      } catch {
        this.editor.commands.focus("end");
      }
      this.visual.scrollTop = snapshot.scroll;
      this.restored = snapshot;
    }
    this.reflectSourceMode();
  }
  restoreViewport(): void {
    const dialog = this.viewport;
    if (dialog && this.restored?.dialogScroll !== undefined)
      dialog.scrollTop = this.restored.dialogScroll;
  }
  restoreFocus(takeFocus = true): void {
    const snapshot = this.restored;
    const dialog = this.viewport;
    const restoreScroll = () => {
      if (dialog && snapshot?.dialogScroll !== undefined)
        dialog.scrollTop = snapshot.dialogScroll;
    };
    if (this.sourceMode) this.source.focus(takeFocus);
    else if (!takeFocus) {
      restoreScroll();
      return;
    } else if (snapshot?.math) {
      const field = this.visual.querySelectorAll("math-field")[
        snapshot.math.index
      ] as ReturnType<typeof makeMath> | undefined;
      if (field && !field.readOnly) {
        this.activeMath = field;
        field.selection = structuredClone(snapshot.math.selection);
        field.addEventListener("focusin", restoreScroll, { once: true });
        field.focus();
      }
    } else this.editor.view.focus();
    restoreScroll();
  }
  private remember(): void {
    if (!this.sourceMode) this.changed(this.value(), this.snapshot());
  }
  private notify(): void {
    this.changed(this.value(), this.snapshot());
    this.updatePreview();
  }
  private updatePreview(): void {
    if (this.preview.hidden) return;
    this.disposePreview?.();
    this.disposePreview = renderDocument(this.preview, this.value());
  }
  value(): string {
    return this.sourceMode
      ? this.source.value
      : serialize(this.editor.getJSON());
  }
  snapshot(): EditorSnapshot {
    const fields = Array.from(this.visual.querySelectorAll("math-field"));
    const index = this.activeMath ? fields.indexOf(this.activeMath) : -1;
    const math =
      index >= 0 && this.activeMath?.selection && !this.sourceMode
        ? { index, selection: structuredClone(this.activeMath.selection) }
        : undefined;
    const result = {
      json: this.editor.getJSON(),
      selection: this.editor.state.selection.from,
      scroll: this.visual.scrollTop,
      sourceMode: this.sourceMode,
      sourceSelection: this.source?.snapshot(),
      dialogScroll: this.viewport?.scrollTop,
      ...(math ? { math } : {}),
    };
    this.restored = result;
    return result;
  }
  valid(): boolean {
    return (
      this.sourceMode || !this.visual.querySelector('[data-invalid="true"]')
    );
  }
  private toggleSource(): void {
    if (this.sourceMode) {
      this.editor.commands.setContent(parseDocument(this.source.value), {
        emitUpdate: false,
      });
      this.editor.commands.setContent(
        normalizedOriginals(this.editor.getJSON()),
        { emitUpdate: false },
      );
    } else this.source.value = this.value();
    this.sourceMode = !this.sourceMode;
    this.visual.hidden = this.sourceMode;
    this.source.host.hidden = !this.sourceMode;
    this.reflectSourceMode();
    if (this.sourceMode) this.source.focus();
    else this.editor.view.focus();
    this.notify();
  }
  private reflectSourceMode(): void {
    for (const group of this.parent.querySelectorAll<HTMLElement>(
      ".document-toolbar .document-tool-group",
    )) {
      if (group.getAttribute("aria-label") !== "Representación del documento")
        group.inert = this.sourceMode;
    }
    const toggle = [
      ...this.parent.querySelectorAll(".document-toolbar button"),
    ].find((button) => button.textContent === "Fuente LaTeX");
    toggle?.setAttribute("aria-pressed", String(this.sourceMode));
  }
  insertLatex(latex: string): boolean {
    if (!this.valid()) return false;
    if (this.sourceMode) {
      this.source.insert(latex);
      return true;
    }
    const parsed = parseDocument(latex);
    return this.editor
      .chain()
      .focus()
      .insertContent(parsed.content || [])
      .run();
  }
  insertFormula(display: boolean): void {
    const before = new Set(this.visual.querySelectorAll("math-field"));
    this.editor.commands.insertContent({
      type: "formula",
      attrs: { latex: "", display, legacy: false },
    });
    const field = Array.from(this.visual.querySelectorAll("math-field")).find(
      (candidate) => !before.has(candidate),
    );
    this.activeMath = field as ReturnType<typeof makeMath> | undefined;
    (field as HTMLElement | undefined)?.focus();
  }
  private editableMath(): ReturnType<typeof makeMath> | undefined {
    if (this.sourceMode) return;
    const active =
      this.visual.getRootNode() instanceof ShadowRoot
        ? (this.visual.getRootNode() as ShadowRoot).activeElement
        : document.activeElement;
    const fields = Array.from(this.visual.querySelectorAll("math-field"));
    return (
      (this.activeMath?.isConnected && !this.activeMath.readOnly
        ? this.activeMath
        : undefined) ??
      (fields.find(
        (field) =>
          field === active && !(field as ReturnType<typeof makeMath>).readOnly,
      ) as ReturnType<typeof makeMath> | undefined) ??
      (fields
        .filter((field) => !(field as ReturnType<typeof makeMath>).readOnly)
        .at(-1) as ReturnType<typeof makeMath> | undefined)
    );
  }
  insertTemplate(template: string): boolean {
    if (this.sourceMode) return false;
    let math = this.editableMath();
    if (!math) {
      this.insertFormula(true);
      math = this.editableMath();
    }
    if (math && "insert" in math) {
      const inserted = (math as ReturnType<typeof makeMath>).insert(template, {
        insertionMode: "replaceSelection",
        selectionMode: "placeholder",
      });
      if (!inserted) return false;
      math.dispatchEvent(new InputEvent("input", { bubbles: true }));
      (math as unknown as HTMLElement).focus();
      return true;
    }
    return false;
  }
  destroy(): void {
    this.disposeKeyboard();
    this.disposePreview?.();
    this.source.destroy();
    this.editor.destroy();
  }
}
/** Preview, reader and editor share exactly the same parser and node views. */
export function renderDocument(
  parent: HTMLElement,
  latex: string,
  preview?: PreviewFigure,
): () => void {
  const reader = new Editor({
    injectCSS: false,
    element: parent,
    extensions: documentExtensions(preview),
    editable: false,
    content: parseDocument(latex),
    editorProps: { attributes: { class: "mathematical-document" } },
  });
  return () => reader.destroy();
}
