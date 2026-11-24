import { afterEach, expect, it, vi } from "vitest";
import type { MathfieldElement } from "mathlive";
import {
  matrixLatex,
  mountFormulaTools,
} from "../src/knowledge-map/formula-tools";
afterEach(() => document.body.replaceChildren());
it.each([
  [1, 1, "pmatrix"],
  [3, 2, "bmatrix"],
  [8, 8, "vmatrix"],
])(
  "constructs a bounded %sx%s %s using editable mathematical cells",
  (rows, columns, environment) => {
    const latex = matrixLatex(
      Number(rows),
      Number(columns),
      String(environment),
    );
    expect(latex).toMatch(/^\\begin\{/);
    expect(latex.endsWith(`\\end{${environment}}`)).toBe(true);
    const body = latex.slice(
      latex.indexOf("}") + 1,
      latex.lastIndexOf("\\end{"),
    );
    const cells = body.split(String.raw`\\`).map((row) => row.split("&"));
    expect(cells).toHaveLength(Number(rows));
    expect(
      cells.every(
        (row) =>
          row.length === Number(columns) && row.every((value) => value === "0"),
      ),
    ).toBe(true);
  },
);
it.each([
  [0, 2, "pmatrix"],
  [2, 9, "pmatrix"],
  [2.5, 2, "pmatrix"],
  [2, NaN, "pmatrix"],
  [2, 2, "evil}"],
])(
  "refuses invalid dimensions or arbitrary TeX environments: %s %s %s",
  (rows, columns, environment) => {
    expect(() =>
      matrixLatex(Number(rows), Number(columns), String(environment)),
    ).toThrow(/entre 1 y 8/);
  },
);
it("filters accent-insensitively and inserts only an explicitly chosen preset", () => {
  const insert = vi.fn(() => true),
    host = document.createElement("div");
  document.body.append(host);
  mountFormulaTools(host, { insert, active: () => undefined });
  const search = host.querySelector<HTMLInputElement>('input[type="search"]')!;
  search.value = "limite";
  search.dispatchEvent(new InputEvent("input"));
  const matches = host.querySelector('[aria-label="Estructuras matemáticas"]')!;
  expect(matches.querySelectorAll("button")).toHaveLength(1);
  expect(insert).not.toHaveBeenCalled();
  matches.querySelector("button")!.click();
  expect(insert).toHaveBeenCalledWith(String.raw`\lim_{x\to 0}#0`);
  search.value = "no existe";
  search.dispatchEvent(new InputEvent("input"));
  expect(matches.textContent).toContain("No hay estructuras");
  expect(insert).toHaveBeenCalledTimes(1);
});
it("does not announce an insertion or history operation when no editable field is available", () => {
  const host = document.createElement("div");
  document.body.append(host);
  mountFormulaTools(host, { insert: () => false, active: () => undefined });
  Array.from(host.querySelectorAll("button"))
    .find((button) => button.textContent === "Fracción")!
    .click();
  expect(host.querySelector('[role="status"]')!.textContent).toContain(
    "fuente original se conserva",
  );
  Array.from(host.querySelectorAll("button"))
    .find((button) => button.textContent === "Deshacer fórmula")!
    .click();
  expect(host.querySelector('[role="status"]')!.textContent).toContain(
    "Selecciona una fórmula",
  );
});
it("dispatches formula history only when MathLive confirms its availability", () => {
  const host = document.createElement("div"),
    field = Object.assign(document.createElement("math-field"), {
      canUndo: () => true,
      canRedo: (): boolean => false,
      executeCommand: vi.fn(),
    });
  document.body.append(host, field);
  const input = vi.fn();
  field.addEventListener("input", input);
  mountFormulaTools(host, {
    insert: () => true,
    active: () => field as unknown as MathfieldElement,
  });
  const button = (name: string) =>
    Array.from(host.querySelectorAll("button")).find(
      (button) => button.textContent === name,
    )!;
  button("Deshacer fórmula").click();
  expect(field.executeCommand).toHaveBeenCalledWith("undo");
  expect(input).toHaveBeenCalledTimes(1);
  button("Rehacer fórmula").click();
  expect(field.executeCommand).toHaveBeenCalledTimes(1);
  expect(host.querySelector('[role="status"]')!.textContent).toContain(
    "No hay cambios",
  );
  field.canRedo = () => true;
  field.executeCommand.mockReturnValueOnce(false);
  button("Rehacer fórmula").click();
  expect(input).toHaveBeenCalledTimes(1);
  expect(host.querySelector('[role="status"]')!.textContent).toContain("No se confirmó");
  field.executeCommand.mockReturnValueOnce(true);
  button("Rehacer fórmula").click();
  expect(field.executeCommand).toHaveBeenLastCalledWith("redo");
  expect(input).toHaveBeenCalledTimes(2);
  expect(host.querySelector('[role="status"]')!.textContent).toContain("rehecho");
});
it("matrix validation leaves the active expression unchanged and valid insertion delegates to MathLive", () => {
  const insert = vi.fn(() => true),
    host = document.createElement("div");
  document.body.append(host);
  mountFormulaTools(host, { insert, active: () => undefined });
  const rows = host.querySelector<HTMLInputElement>('input[type="number"]')!,
    button = Array.from(host.querySelectorAll("button")).find(
      (button) => button.textContent === "Insertar matriz configurable",
    )!;
  rows.value = "99";
  button.click();
  expect(insert).not.toHaveBeenCalled();
  expect(host.querySelector('[role="status"]')!.textContent).toContain(
    "entre 1 y 8",
  );
  rows.value = "3";
  button.click();
  expect(insert).toHaveBeenCalledWith(
    String.raw`\begin{pmatrix}0&0\\0&0\\0&0\end{pmatrix}`,
  );
});
