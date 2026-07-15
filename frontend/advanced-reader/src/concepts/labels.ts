import type { EvidenceLinkType } from "../types/api";

export const EVIDENCE_LINK_OPTIONS: ReadonlyArray<{
  value: EvidenceLinkType;
  label: string;
  help: string;
}> = [
  { value: "definition_source", label: "Fuente de definición", help: "Define o introduce formalmente el concepto." },
  { value: "theorem_source", label: "Fuente de teorema", help: "Enuncia un resultado central sobre el concepto." },
  { value: "proof_source", label: "Fuente de prueba", help: "Contiene una demostración o justificación." },
  { value: "example_source", label: "Fuente de ejemplo", help: "Presenta una instancia concreta del concepto." },
  { value: "motivation", label: "Motivación", help: "Explica por qué el concepto resulta útil o natural." },
  { value: "citation", label: "Cita", help: "Registra una cita especialmente relevante." },
  { value: "question", label: "Pregunta", help: "Plantea una pregunta abierta o de lectura." },
  { value: "related_context", label: "Contexto relacionado", help: "Ayuda a comprender el concepto sin definirlo." },
];

export function evidenceLinkLabel(value: EvidenceLinkType): string {
  return EVIDENCE_LINK_OPTIONS.find((item) => item.value === value)?.label ?? value;
}
