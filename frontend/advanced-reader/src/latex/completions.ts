/** Editing aids, not a TeX parser: inserted snippets always remain ordinary source. */
import {
  snippetCompletion,
  type CompletionContext,
} from "@codemirror/autocomplete";

const environments = [
  ["definition", "Definición", true],
  ["theorem", "Teorema", true],
  ["lemma", "Lema", true],
  ["proposition", "Proposición", true],
  ["example", "Ejemplo", true],
  ["remark", "Nota", true],
  ["context", "Contexto", false],
  ["reference", "Referencia", false],
  ["proof", "Demostración", false],
  ["align*", "Ecuaciones alineadas", false],
  ["cases", "Sistema por casos", false],
  ["itemize", "Lista", false],
  ["tikzpicture", "Figura TikZ", false],
] as const;

export const latexSnippets = environments.map(([name, label, titled]) => ({
  name,
  label,
  // The title argument is mandatory in the real miestilo environments.
  template: `\\begin{${name}}${titled ? "{${Título}}" : ""}\n${name === "itemize" ? "\\item " : ""}\${Contenido}\n\\end{${name}}`,
}));

const commands = [
  ["frac", "\\frac{${Numerador}}{${Denominador}}"],
  ["sqrt", "\\sqrt{${Expresión}}"],
  ["textbf", "\\textbf{${Texto}}"],
  ["emph", "\\emph{${Texto}}"],
  ["label", "\\label{${Identidad}}"],
  ["ref", "\\ref{${Identidad}}"],
  ["href", "\\href{${URL}}{${Texto}}"],
  ["cite", "\\cite{${Referencia}}"],
  ["newcommand", "\\newcommand{\\${Nombre}}[1]{${Definición}}"],
  ["usepackage", "\\usepackage{${Paquete}}"],
] as const;

export function latexCompletion(context: CompletionContext) {
  const token = context.matchBefore(/\\[A-Za-z]*(?:\{[A-Za-z*]*)?/u);
  if (!token) return null;
  const options = token.text.startsWith("\\begin{")
    ? latexSnippets.map(({ name, label, template }) =>
        snippetCompletion(template, {
          label: `\\begin{${name}}`,
          detail: label,
          type: "keyword",
        }),
      )
    : [
        ...commands.map(([name, template]) =>
          snippetCompletion(template, { label: "\\" + name, type: "function" }),
        ),
        ...latexSnippets.map(({ name, label, template }) =>
          snippetCompletion(template, {
            label: `\\begin{${name}}`,
            detail: label,
            type: "keyword",
          }),
        ),
      ];
  return { from: token.from, options, validFor: /^[\\A-Za-z{*]*$/u };
}
