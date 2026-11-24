import { writeSource } from "./source-code-support";
import { afterEach, describe, expect, it, vi } from "vitest";
import { DocumentEditor } from "../src/knowledge-map/document-editor";
import { mountMathKeyboard } from "../src/knowledge-map/keyboard";

const { dispose } = vi.hoisted(() => ({ dispose: vi.fn() }));
vi.mock("../src/knowledge-map/keyboard", () => ({
  mountMathKeyboard: vi.fn(() => dispose),
}));
vi.mock("../src/knowledge-map/math", () => ({
  makeMath: (value: string, editable: boolean) =>
    Object.assign(document.createElement("math-field"), {
      value,
      readOnly: !editable,
      selection: { ranges: [[0, 0]], direction: "forward" },
    }),
  mathErrors: () => [],
}));
afterEach(() => {
  document.body.replaceChildren();
  vi.clearAllMocks();
});

describe("wide document editor lifecycle", () => {
  it("creates nested study and mathematical blocks plus an explicitly protected TikZ fragment", () => {
    const host = document.createElement("div");
    document.body.append(host);
    const editor = new DocumentEditor(host, "", () => {});
    const select = host.querySelector<HTMLSelectElement>(
      '[aria-label="Insertar bloque de estudio"]',
    )!;
    select.value = "context";
    select.dispatchEvent(new Event("change"));
    editor.editor.commands.insertContent("Contexto escrito visualmente.");
    const result = host.querySelector<HTMLSelectElement>(
      '[aria-label="Insertar bloque de resultado"]',
    )!;
    result.value = "definition";
    result.dispatchEvent(new Event("change"));
    editor.editor.commands.insertContent("Definición anidada.");
    const button = Array.from(host.querySelectorAll("button")).find(
      (b) => b.textContent === "Bloque LaTeX avanzado",
    )!;
    button.click();
    const input = document.querySelector<HTMLTextAreaElement>(
      ".source-block-dialog textarea",
    )!;
    const tikz = String.raw`\begin{tikzpicture}\draw (0,0)--(1,1);\end{tikzpicture}`;
    input.value = tikz;
    Array.from(
      document.querySelectorAll<HTMLButtonElement>(
        ".source-block-dialog button",
      ),
    )
      .find((b) => b.textContent === "Conservar bloque")!
      .click();
    const latex = editor.value();
    expect(latex).toContain("\\begin{context}\n");
    expect(latex).toContain("\\begin{definition}{}\n");
    expect(latex).toContain(tikz);
    expect(latex.indexOf("\\begin{context}")).toBeLessThan(
      latex.indexOf("\\begin{definition}"),
    );
    editor.editor.commands.insertContentAt(
      editor.editor.state.doc.content.size - 1,
      " Texto adicional.",
    );
    expect(editor.value()).toContain(tikz);
    editor.destroy();
  });
  it("mounts the keyboard on its owned page, restores scroll and destroys the adapter", () => {
    const viewport = document.createElement("section"),
      host = document.createElement("div");
    viewport.append(host);
    document.body.append(viewport);
    const editor = new DocumentEditor(
      host,
      "Una nota con $x$ y contenido.",
      () => {},
      undefined,
      { keyboardContainer: viewport, viewport },
    );
    expect(mountMathKeyboard).toHaveBeenCalledWith(viewport);
    expect(host.closest("dialog")).toBeNull();
    viewport.scrollTop = 280;
    const snapshot = editor.snapshot();
    expect(snapshot.dialogScroll).toBe(280);
    const original = editor.value();
    editor.destroy();
    host.replaceChildren();
    viewport.scrollTop = 0;
    const recovered = new DocumentEditor(host, original, () => {}, snapshot, {
      keyboardContainer: viewport,
      viewport,
    });
    recovered.restoreViewport();
    expect(viewport.scrollTop).toBe(280);
    expect(recovered.value()).toBe(original);
    recovered.destroy();
    expect(dispose).toHaveBeenCalledTimes(2);
  });
  it("preserves unsupported original LaTeX when ordinary prose is edited on the page", () => {
    const viewport = document.createElement("section"),
      host = document.createElement("div");
    viewport.append(host);
    document.body.append(viewport);
    const legacy = String.raw`\begin{tikzpicture}\draw (0,0) -- (1,1);\end{tikzpicture}`;
    const editor = new DocumentEditor(
      host,
      legacy + "\n\nTexto original.",
      () => {},
      undefined,
      { keyboardContainer: viewport, viewport },
    );
    editor.editor.commands.insertContentAt(
      editor.editor.state.doc.content.size - 1,
      " Otra observación.",
    );
    expect(editor.value()).toContain(legacy);
    expect(editor.value()).toContain("Otra observación.");
    editor.destroy();
  });
});

it("compiles the current canonical snapshot from both visual and full source modes without saving", () => {
  const host = document.createElement("div"), viewport = document.createElement("div");
  document.body.append(viewport); viewport.append(host);
  const compiled = vi.fn(), changed = vi.fn();
  const editor = new DocumentEditor(host, "Original", changed, undefined, {keyboardContainer: viewport, viewport, compiled});
  editor.editor.commands.insertContent("Texto nuevo. ");
  const button = (name: string) => [...host.querySelectorAll("button")].find(b => b.textContent === name)!;
  button("Vista compilada").click();
  expect(compiled.mock.calls[0][0]).toBe(editor.value());
  expect(compiled.mock.calls[0][0]).toContain("Texto nuevo.");
  button("Fuente LaTeX").click();
  const full = String.raw`\documentclass{article}\newcommand{\foo}{Valor}\begin{document}\foo\end{document}`;
  writeSource(host, full);
  button("Vista compilada").click();
  expect(compiled.mock.calls[1][0]).toBe(full);
  expect(editor.value()).toBe(full);
  expect(changed.mock.calls.at(-1)![0]).toBe(full);
  editor.destroy();
});
