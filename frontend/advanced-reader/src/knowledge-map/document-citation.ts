/** Citation UI lifecycle, separate from the document's text and the map scene. */
import { element, button, field } from "./ui";
import {
  renderBibliography,
  emptyLocator,
  referenceLabel,
} from "./bibliography";
import type { Draft } from "./model";
export class DocumentCitation {
  private disposePicker?: () => void;
  private summary = element("section", "", "document-citation");
  constructor(
    private dialog: HTMLDialogElement,
    form: HTMLFormElement,
    private draft: Draft,
    private save: () => void,
    private send: (payload: Record<string, unknown>) => void,
    private focusDocument: () => void,
  ) {
    button("Buscar o añadir referencia", () => this.open(), form);
    form.append(this.summary);
    this.renderSummary();
  }
  private renderSummary(): void {
    this.summary.replaceChildren();
    if (!this.draft.referenceId) return;
    const { draft } = this;
    this.summary.append(
      element(
        "p",
        draft.reference
          ? referenceLabel(draft.reference)
          : `Referencia: ${draft.referenceId}`,
      ),
    );
    const locator = (draft.referenceLocator ??= emptyLocator());
    const details = element("details");
    details.append(element("summary", "Localizador de este pasaje"));
    const fields = [
      ["printed_page", "Página impresa"],
      ["chapter", "Capítulo"],
      ["section", "Sección"],
      ["theorem", "Teorema"],
      ["passage", "Pasaje citado"],
    ] as const;
    fields.forEach(([key, label]) =>
      field(
        details,
        label,
        locator[key],
        (value) => {
          locator[key] = value;
          this.save();
        },
        key === "passage",
      ),
    );
    field(
      details,
      "Página física del PDF (sin deducir página impresa)",
      locator.pdf_page === null ? "" : String(locator.pdf_page),
      (value) => {
        locator.pdf_page = value ? Number(value) : null;
        this.save();
      },
    );
    details.append(
      element(
        "p",
        "Un índice indicado manualmente no vincula un archivo. Los PDF se asocian y abren desde el lector.",
      ),
    );
    this.summary.append(details);
  }
  open(): void {
    this.draft.bibliography ??= {
      open: true,
      query: "",
      title: "",
      author: "",
      status: "idle",
      candidates: [],
    };
    this.draft.bibliography.open = true;
    this.save();
    this.disposePicker?.();
    this.disposePicker = renderBibliography(
      this.dialog,
      this.draft.bibliography,
      this.send,
      this.draft.source,
      this.save,
      () => {
        this.disposePicker?.();
        this.disposePicker = undefined;
        this.renderSummary();
        this.focusDocument();
      },
    );
  }
  restore(): void {
    if (this.draft.bibliography?.open) this.open();
  }
  destroy(): void {
    this.disposePicker?.();
    this.disposePicker = undefined;
  }
}
