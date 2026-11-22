import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { fireEvent, getByRole, getByLabelText } from "@testing-library/dom";
import { openReader } from "../src/knowledge-map/reader";
import type { Node } from "../src/knowledge-map/model";

// Rendering uses the same real Tiptap schema/LaTeX adapter as the editor. The
// vendor mathfield itself has browser acceptance tests, so no fake HTML is parsed.
vi.mock("../src/knowledge-map/math", () => ({
  makeMath: (latex: string) =>
    Object.assign(document.createElement("math-field"), { value: latex }),
  mathErrors: () => [],
}));
let parent: HTMLElement, dispose: (() => void) | undefined;
const node: Node = {
  key: "same@source",
  id: "same",
  source: "Fuente exacta",
  titulo: "Título <img onerror=bad()>",
  tipo: "teorema",
  comentario: "",
  categorias: [],
  revision: "r",
  referencia: { autor: "Autor", paginas: "42–43" },
  contenido_latex: String.raw`\begin{theorem}{Resultado}Texto con $x^2$.\begin{itemize}\item Uno\item Dos\end{itemize}\end{theorem}`,
};
beforeEach(() => {
  parent = document.createElement("div");
  document.body.append(parent);
  HTMLDialogElement.prototype.showModal = function () {
    this.open = true;
  };
  HTMLDialogElement.prototype.close = function () {
    this.open = false;
    this.dispatchEvent(new Event("close"));
  };
});
afterEach(() => {
  dispose?.();
  dispose = undefined;
  parent.remove();
});
it("shows complete structured content, safe metadata and the exact original source", () => {
  const closed = vi.fn();
  dispose = openReader(parent, node, 19, closed);
  expect(getByRole(parent, "heading", { name: node.titulo })).toBeVisible();
  expect(parent.querySelector("img")).toBeNull();
  expect(
    parent.querySelector('[data-result="theorem"]')?.textContent,
  ).toContain("Texto con");
  expect(parent.querySelectorAll("li")).toHaveLength(2);
  expect(parent.textContent).toContain("paginas: 42–43");
  expect(parent.querySelector("pre")?.textContent).toBe(node.contenido_latex);
  fireEvent.input(getByLabelText(parent, "Tamaño de lectura"), {
    target: { value: "24" },
  });
  expect((parent.querySelector("article") as HTMLElement).style.fontSize).toBe(
    "24px",
  );
  fireEvent.click(getByRole(parent, "button", { name: "Cerrar lectura" }));
  expect(parent.querySelector("dialog")).toBeNull();
  expect(closed).toHaveBeenCalledTimes(1);
  dispose();
  expect(closed).toHaveBeenCalledTimes(1);
});
it("cleans a replaced reader without allowing its old snapshot to overwrite the new selection", () => {
  dispose = openReader(parent, node, 20, () => {});
  dispose();
  const next = {
    ...node,
    titulo: "Otra selección",
    key: "other@source",
    contenido_latex: "Contenido posterior",
  };
  dispose = openReader(parent, next, 18, () => {});
  expect(parent.querySelectorAll("dialog")).toHaveLength(1);
  expect(parent.querySelector("article")?.textContent).toContain(
    "Contenido posterior",
  );
  expect(parent.querySelector("h2")?.textContent).toBe(next.titulo);
});
