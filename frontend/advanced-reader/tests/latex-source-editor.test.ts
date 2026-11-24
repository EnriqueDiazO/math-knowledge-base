import { sourceRoot } from "./source-code-support";
import { afterEach, describe, expect, it, vi } from "vitest";
import { CompletionContext } from "@codemirror/autocomplete";
import { EditorSelection, EditorState } from "@codemirror/state";
import { LatexSourceEditor } from "../src/latex/source-editor";
import { latexCompletion } from "../src/latex/completions";

const editors: LatexSourceEditor[] = [];
const mount = (value = "") => {
  const host = document.createElement("div");
  document.body.append(host);
  const changed = vi.fn(),
    editor = new LatexSourceEditor(host, value, changed);
  editors.push(editor);
  return { editor, host, changed };
};
afterEach(() => {
  editors.forEach((e) => e.destroy());
  editors.length = 0;
  document.body.replaceChildren();
});
const button = (host: HTMLElement, name: string) =>
  [...host.querySelectorAll("button")].find((b) => b.textContent === name)!;

describe("lossless full LaTeX source editor", () => {
  it.each([
    "a\r\nb\r\nc",
    "a\nb\r\nc\n",
    "á ∑ \\未知{😀}\n",
    "\\documentclass{article}\n\\begin{document}\n\\macro{sin convertir}\n\\end{document}\n",
  ])(
    "preserves every source character including mixed line endings: %j",
    (source) => {
      const { editor, changed } = mount(source);
      expect(editor.value).toBe(source);
      expect(changed).not.toHaveBeenCalled();
      const position = source.indexOf("b");
      if (position >= 0) {
        editor.view.dispatch({
          changes: { from: position, to: position + 1, insert: "B" },
        });
        expect(editor.value).toBe(
          source.slice(0, position) + "B" + source.slice(position + 1),
        );
      }
    },
  );
  it("replaces only the selection, supports undo/redo and retains history across no-op assignment", () => {
    const { editor, host, changed } = mount("Antes\nSeleccionado\nDespués");
    editor.view.dispatch({ selection: EditorSelection.single(6, 18) });
    editor.view.dispatch(editor.view.state.replaceSelection("Revisado"));
    expect(editor.value).toBe("Antes\nRevisado\nDespués");
    expect(changed).toHaveBeenCalled();
    const unchanged = editor.value;
    editor.value = unchanged;
    button(host, "Deshacer código").click();
    expect(editor.value).toBe("Antes\nSeleccionado\nDespués");
    button(host, "Rehacer código").click();
    expect(editor.value).toBe("Antes\nRevisado\nDespués");
  });
  it("inserts a paired semantic environment with the real mandatory title and selected snippet field", () => {
    const { editor, host } = mount("Prosa intacta.\n");
    editor.view.dispatch({ selection: { anchor: editor.value.length } });
    const select = host.querySelector("select")!;
    select.value = "definition";
    select.dispatchEvent(new Event("change"));
    expect(editor.value).toBe(
      "Prosa intacta.\n\\begin{definition}{Título}\nContenido\n\\end{definition}",
    );
    expect(
      editor.view.state.sliceDoc(
        editor.view.state.selection.main.from,
        editor.view.state.selection.main.to,
      ),
    ).toBe("Título");
  });
  it("offers installed command and environment completions without parsing unrelated prose", () => {
    const complete = (value: string) =>
      latexCompletion(
        new CompletionContext(
          EditorState.create({ doc: value }),
          value.length,
          true,
        ),
      );
    expect(complete("texto normal")).toBeNull();
    expect(complete("\\fra")!.options.map((o) => o.label)).toContain("\\frac");
    expect(complete("\\begin{def")!.options.map((o) => o.label)).toContain(
      "\\begin{definition}",
    );
  });
  it("finds, replaces and undoes a literal search through CodeMirror's real panel", () => {
    const { editor, host } = mount("ámbito x\nmacro x\n");
    button(host, "Buscar y reemplazar").click();
    const search = sourceRoot(host).querySelector<HTMLInputElement>(
      'input[name="search"]',
    )!;
    search.value = "macro";
    search.dispatchEvent(new Event("change", { bubbles: true }));
    const replacement = sourceRoot(host).querySelector<HTMLInputElement>(
      'input[name="replace"]',
    )!;
    replacement.value = "definición";
    replacement.dispatchEvent(new Event("change", { bubbles: true }));
    sourceRoot(host)
      .querySelector<HTMLButtonElement>('button[name="replaceAll"]')!
      .click();
    expect(editor.value).toBe("ámbito x\ndefinición x\n");
    button(host, "Deshacer código").click();
    expect(editor.value).toBe("ámbito x\nmacro x\n");
  });
  it("restores a bounded selection and scroll without changing the document", () => {
    const { editor, changed } = mount("Uno\nDos");
    editor.restore({ anchor: 5, head: 200, scrollTop: 24, scrollLeft: 10 });
    expect(editor.snapshot()).toMatchObject({
      anchor: 5,
      head: 7,
      scrollTop: 24,
      scrollLeft: 10,
    });
    expect(editor.value).toBe("Uno\nDos");
    expect(changed).toHaveBeenCalled();
  });
  it("rejects invalid line navigation, then moves to the requested real line", () => {
    const { editor, host } = mount("Una\nDos\nTres");
    const input = host.querySelector<HTMLInputElement>('input[type="number"]')!;
    input.value = "99";
    button(host, "Ir").click();
    expect(host.querySelector('[role="status"]')!.textContent).toContain(
      "1 y 3",
    );
    input.value = "3";
    button(host, "Ir").click();
    expect(editor.view.state.selection.main.head).toBe(8);
    expect(editor.value).toBe("Una\nDos\nTres");
  });
});

it("restores only supported heights and handles an unusable saved cursor without losing source", () => {
  const { editor, host } = mount("Fuente conservada\nSegunda línea");
  editor.restore({
    anchor: Number.NaN,
    head: 999,
    scrollTop: 0,
    scrollLeft: 0,
    height: "20rem",
  });
  expect(editor.snapshot()).toMatchObject({
    anchor: 0,
    head: 31,
    height: "20rem",
  });
  expect(
    host.querySelector<HTMLElement>(".latex-source-viewport")!.style.height,
  ).toBe("20rem");
  editor.restore({
    ...editor.snapshot(),
    height: "url(https://invalid.example)",
  });
  expect(editor.snapshot().height).toBe("20rem");
  expect(editor.value).toBe("Fuente conservada\nSegunda línea");
});
it("does not insert a fragment when the placeholder option is selected", () => {
  const { editor, host } = mount("Original");
  const select = host.querySelector<HTMLSelectElement>(
    '[aria-label="Insertar fragmento LaTeX"]',
  )!;
  select.value = "";
  select.dispatchEvent(new Event("change"));
  expect(editor.value).toBe("Original");
});
