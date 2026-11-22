/** Screen adaptations of templates_latex/miestilo.sty. Never export these colors. */
import definitions from "../../../../editor/ui/concept_types.json";

export const conceptTypes = definitions;
export type ConceptKind = keyof typeof definitions;
export function conceptKind(value: string): ConceptKind | undefined {
  const normalized = value
    .normalize("NFD")
    .replace(/\p{Diacritic}/gu, "")
    .toLowerCase();
  return (Object.keys(definitions) as ConceptKind[]).find((key) =>
    definitions[key].aliases.includes(normalized),
  );
}
export function conceptType(value: string) {
  const key = conceptKind(value);
  return key ? definitions[key] : undefined;
}
export function applyConceptTheme(root: HTMLElement): void {
  Object.entries(definitions).forEach(([key, type]) => {
    for (const field of ["accent", "background", "border"] as const)
      root.style.setProperty(`--concept-${key}-${field}`, type[field]);
  });
}
/** One insertion choice per family; aliases remain accepted by the parser. */
export const resultChoices = [
  "definition",
  "theorem",
  "corollary",
  "lemma",
  "proposition",
  "example",
  "remark",
  "observation",
  "proof",
];
export const resultNames: Record<string, string> = {
  ...Object.fromEntries(
    Object.values(definitions).flatMap((type) =>
      type.aliases.map((alias) => [alias, type.label]),
    ),
  ),
  proof: "Demostración",
};
