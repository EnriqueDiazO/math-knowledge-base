/** Resolve evidence by canonical identities. A title or a nearby node is no join key. */
import type { Data, Node } from "./model";
import { element, button } from "./ui";
export type SourceLink = {
  documentId: string;
  annotationId?: string;
  noteId?: string;
  label: string;
  quote: string;
  printedPage: string;
  pdfPage: number | null;
  exact: boolean;
};
export function conceptSources(node: Node, data: Data): SourceLink[] {
  const result: SourceLink[] = [];
  for (const link of data.evidence ?? []) {
    if (
      link.concept_legacy_id !== node.id ||
      link.concept_legacy_source !== node.source
    )
      continue;
    const mark = data.annotations?.find(
      (a) => a.annotation_id === link.annotation_id,
    );
    const note = data.notes?.find((n) => n.note_id === link.note_id);
    const documentId =
      link.document_id || mark?.document_id || note?.document_id;
    const doc = data.documents?.find(
      (d) => d.document_id === documentId && d.source_id === link.source_id,
    );
    if (!doc) continue;
    result.push({
      documentId: doc.document_id,
      ...(mark ? { annotationId: mark.annotation_id } : {}),
      ...(note ? { noteId: note.note_id } : {}),
      label: doc.title,
      quote: mark?.quote_text ?? note?.reference_locator?.passage ?? "",
      printedPage:
        mark?.page_label ?? note?.reference_locator?.printed_page ?? "",
      pdfPage:
        doc.kind === "pdf"
          ? (mark?.page_number ?? note?.page_start ?? link.page_number ?? null)
          : null,
      exact: !!(mark || note?.page_start || link.page_number),
    });
  }
  if (!result.length && node.reference_id)
    for (const doc of data.documents ?? []) {
      if (doc.reference_id !== node.reference_id) continue;
      result.push({
        documentId: doc.document_id,
        label: doc.title,
        quote: "",
        printedPage: "",
        pdfPage: null,
        exact: false,
      });
    }
  return result;
}
export function renderConceptSources(
  parent: HTMLElement,
  node: Node,
  data: Data,
  send: (key: string, value: unknown) => void,
): void {
  const links = conceptSources(node, data);
  if (!links.length) return;
  const section = element("section", "", "concept-provenance");
  section.append(element("h3", "Fuentes y pasajes registrados"));
  links.forEach((link) => {
    const item = element("article");
    item.append(element("h4", link.label));
    if (link.quote) item.append(element("blockquote", link.quote));
    if (link.printedPage)
      item.append(
        element("p", "Página impresa registrada: " + link.printedPage),
      );
    if (link.pdfPage !== null)
      item.append(element("p", "Índice físico del PDF: " + link.pdfPage));
    if (!link.exact)
      item.append(
        element(
          "p",
          "Referencia general; no se ha registrado un pasaje específico para este enlace.",
        ),
      );
    button(
      link.annotationId
        ? "Volver al pasaje de la anotación"
        : link.noteId
          ? "Abrir fuente de la nota"
          : "Abrir fuente asociada",
      () =>
        send("open_source", {
          document_id: link.documentId,
          ...(link.annotationId ? { annotation_id: link.annotationId } : {}),
          ...(link.noteId ? { note_id: link.noteId } : {}),
        }),
      item,
    );
    section.append(item);
  });
  parent.append(section);
}
