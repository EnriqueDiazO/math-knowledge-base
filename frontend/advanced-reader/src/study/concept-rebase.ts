/** Explicit conflict recovery keeps local edits and adopts untouched remote fields. */
import type { Draft } from "../knowledge-map/model";
import type { ConceptDetail } from "./api";
export function rebaseConcept(
  local: Draft,
  before: ConceptDetail,
  remote: ConceptDetail,
): Draft {
  if (
    before.key !== remote.key ||
    before.tipo !== remote.tipo ||
    before.source !== remote.source
  )
    throw new Error(
      "La identidad del concepto cambió. Descarga el borrador y vuelve a abrir su ficha.",
    );
  const bodyUnchanged = local.content === before.contenido_latex;
  const sameLocator =
    JSON.stringify(local.referenceLocator ?? null) ===
    JSON.stringify(before.reference_locator ?? null);
  return {
    ...local,
    title: local.title === before.titulo ? remote.titulo : local.title,
    content: bodyUnchanged ? remote.contenido_latex : local.content,
    document: bodyUnchanged ? undefined : local.document,
    comment:
      local.comment === (before.comentario || "")
        ? remote.comentario || ""
        : local.comment,
    categories:
      local.categories === before.categorias.join(", ")
        ? remote.categorias.join(", ")
        : local.categories,
    referenceId:
      local.referenceId === (before.reference_id || undefined)
        ? remote.reference_id || undefined
        : local.referenceId,
    referenceLocator: sameLocator
      ? (remote.reference_locator ?? undefined)
      : local.referenceLocator,
    revision: remote.revision,
  };
}
