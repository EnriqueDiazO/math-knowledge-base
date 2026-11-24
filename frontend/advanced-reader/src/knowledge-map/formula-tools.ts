/** Small, independently implemented tools over MathLive, not a second formula engine. */
import type { MathfieldElement } from "mathlive";

export const formulaChoices = [
  { name: "Fracción", group: "Estructuras", latex: String.raw`\frac{#0}{#?}` },
  { name: "Raíz cuadrada", group: "Estructuras", latex: String.raw`\sqrt{#0}` },
  { name: "Potencia", group: "Estructuras", latex: "#0^{#?}" },
  { name: "Subíndice", group: "Estructuras", latex: "#0_{#?}" },
  {
    name: "Paréntesis",
    group: "Delimitadores",
    latex: String.raw`\left(#0\right)`,
  },
  {
    name: "Valor absoluto",
    group: "Delimitadores",
    latex: String.raw`\left|#0\right|`,
  },
  {
    name: "Norma",
    group: "Delimitadores",
    latex: String.raw`\left\lVert#0\right\rVert`,
  },
  {
    name: "Sumatoria",
    group: "Operadores",
    latex: String.raw`\sum_{i=1}^{n}#0`,
  },
  {
    name: "Producto",
    group: "Operadores",
    latex: String.raw`\prod_{i=1}^{n}#0`,
  },
  { name: "Límite", group: "Operadores", latex: String.raw`\lim_{x\to 0}#0` },
  {
    name: "Integral definida",
    group: "Operadores",
    latex: String.raw`\int_{0}^{1}#0\,dx`,
  },
  {
    name: "Sistema por casos",
    group: "Estructuras",
    latex: String.raw`\begin{cases}x+y=1\\x-y=0\end{cases}`,
  },
  {
    name: "Ecuaciones alineadas",
    group: "Estructuras",
    latex: String.raw`\begin{aligned}a&=b+c\\d&=e\end{aligned}`,
  },
] as const;

export function matrixLatex(
  rows: number,
  columns: number,
  environment: string,
) {
  if (
    !Number.isInteger(rows) ||
    !Number.isInteger(columns) ||
    rows < 1 ||
    rows > 8 ||
    columns < 1 ||
    columns > 8 ||
    !["pmatrix", "bmatrix", "vmatrix"].includes(environment)
  )
    throw new Error(
      "Elige entre 1 y 8 filas y columnas y un delimitador admitido. La fórmula se conserva.",
    );
  const body = Array.from({ length: rows }, () =>
    Array.from({ length: columns }, () => "0").join("&"),
  ).join(String.raw`\\`);
  return `\\begin{${environment}}${body}\\end{${environment}}`;
}
function element<K extends keyof HTMLElementTagNameMap>(tag: K, text = "") {
  const node = document.createElement(tag);
  node.textContent = text;
  return node;
}
function action(parent: HTMLElement, label: string, run: () => void) {
  const button = element("button", label);
  button.type = "button";
  button.onmousedown = (event) => event.preventDefault();
  button.onclick = run;
  parent.append(button);
}
export function mountFormulaTools(
  parent: HTMLElement,
  ports: {
    insert: (latex: string) => boolean;
    active: () => MathfieldElement | undefined;
  },
) {
  const details = element("details"),
    summary = element("summary", "Más herramientas matemáticas"),
    body = element("div"),
    status = element("p");
  details.className = "formula-tools";
  body.className = "formula-tools-panel";
  status.setAttribute("role", "status");
  const insert = (latex: string) => {
    status.textContent = ports.insert(latex)
      ? "Estructura insertada en la fórmula. Completa sus casillas antes de guardar."
      : "Abre la vista visual y selecciona una fórmula editable. La fuente original se conserva.";
  };
  const history = element("div");
  history.setAttribute("role", "group");
  history.setAttribute("aria-label", "Historial de la fórmula activa");
  for (const [label, command] of [
    ["Deshacer fórmula", "undo"],
    ["Rehacer fórmula", "redo"],
  ] as const)
    action(history, label, () => {
      const field = ports.active();
      if (!field) {
        status.textContent =
          "Selecciona una fórmula editable para usar su historial.";
        return;
      }
      const available = command === "undo" ? field.canUndo() : field.canRedo();
      if (!available) {
        status.textContent =
          "No hay cambios de fórmula para " +
          (command === "undo" ? "deshacer." : "rehacer.");
        return;
      }
      if (field.executeCommand(command) === false) {
        status.textContent =
          "No se confirmó el cambio de fórmula. Su contenido se conserva.";
        return;
      }
      field.dispatchEvent(new InputEvent("input", { bubbles: true }));
      field.focus();
      status.textContent =
        command === "undo"
          ? "Cambio de fórmula deshecho."
          : "Cambio de fórmula rehecho.";
    });
  const label = element("label", "Buscar estructura matemática"),
    search = element("input"),
    list = element("div");
  search.type = "search";
  label.append(search);
  list.setAttribute("role", "group");
  list.setAttribute("aria-label", "Estructuras matemáticas");
  const filter = () => {
    list.replaceChildren();
    const needle = search.value
      .normalize("NFD")
      .replace(/\p{M}/gu, "")
      .toLowerCase();
    const choices = formulaChoices.filter((item) =>
      (item.name + " " + item.group)
        .normalize("NFD")
        .replace(/\p{M}/gu, "")
        .toLowerCase()
        .includes(needle),
    );
    for (const item of choices)
      action(list, item.name, () => insert(item.latex));
    if (!choices.length)
      list.append(
        element(
          "p",
          "No hay estructuras para esa búsqueda. Usa el teclado MathLive o la fuente LaTeX.",
        ),
      );
  };
  search.oninput = filter;
  filter();
  const matrix = element("fieldset"),
    legend = element("legend", "Matriz configurable");
  matrix.append(legend);
  const dimension = (text: string) => {
    const label = element("label", text),
      input = element("input");
    input.type = "number";
    input.min = "1";
    input.max = "8";
    input.step = "1";
    input.value = "2";
    label.append(input);
    matrix.append(label);
    return input;
  };
  const rows = dimension("Filas de la matriz"),
    columns = dimension("Columnas de la matriz"),
    delimiter = element("select"),
    delimiterLabel = element("label", "Delimitadores de la matriz");
  delimiter.setAttribute("aria-label", "Delimitadores de la matriz");
  delimiter.append(
    new Option("Paréntesis", "pmatrix"),
    new Option("Corchetes", "bmatrix"),
    new Option("Determinante", "vmatrix"),
  );
  delimiterLabel.append(delimiter);
  matrix.append(delimiterLabel);
  matrix.append(
    element(
      "p",
      "Se insertan ceros editables. La inserción respeta la selección de la fórmula activa.",
    ),
  );
  action(matrix, "Insertar matriz configurable", () => {
    try {
      insert(
        matrixLatex(Number(rows.value), Number(columns.value), delimiter.value),
      );
    } catch (error) {
      status.textContent = (error as Error).message;
    }
  });
  body.append(history, label, list, matrix, status);
  details.append(summary, body);
  parent.append(details);
  return details;
}
