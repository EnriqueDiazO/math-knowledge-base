/** Disposable UI for one explicitly requested figure; rendering never starts TeX. */
import { studyBinary, studyRequest, type StudyContext } from "./api";
import { downloadDocument } from "./api";
import { pngDataUri } from "./image-data";
type Preview = {
  state: string;
  preview_id?: string;
  message: string;
  diagnostic?: string;
  cached?: boolean;
};
const element = <K extends keyof HTMLElementTagNameMap>(tag: K, text = "") => {
  const node = document.createElement(tag);
  node.textContent = text;
  return node;
};
export class FigurePreview {
  private readonly controller = new AbortController();
  private readonly dialogs = new Set<HTMLDialogElement>();
  private active = true;
  constructor(
    private readonly context: Pick<StudyContext, "library_id" | "runtime_id">,
  ) {}
  show = (source: string, host: HTMLElement) => {
    if (!this.active) return;
    const existing = host.querySelector<HTMLElement>(".figure-preview");
    if (existing) {
      existing.scrollIntoView({ block: "nearest" });
      return;
    }
    const panel = element("section");
    panel.className = "figure-preview";
    const status = element("p");
    status.setAttribute("role", "status");
    const image = element("img");
    image.alt = "Vista previa de la figura LaTeX";
    image.hidden = true;
    const refresh = element("button", "Actualizar vista previa");
    refresh.type = "button";
    const zoom = element("button", "Ampliar figura");
    zoom.type = "button";
    zoom.disabled = true;
    const pdf = element("button", "Descargar figura PDF");
    pdf.type = "button";
    pdf.disabled = true;
    const diagnostics = element("details"),
      summary = element("summary", "Detalles de compilación"),
      log = element("pre");
    diagnostics.hidden = true;
    diagnostics.append(summary, log);
    let identifier = "",
      busy = false,
      currentUrl = "",
      confirmedMessage = "";
    image.onload = () => {
      if (!this.active || !panel.isConnected) return;
      if (image.naturalWidth > 0) {
        zoom.disabled = false;
        status.textContent = confirmedMessage;
      }
    };
    image.onerror = () => {
      if (this.active && panel.isConnected) {
        zoom.disabled = true;
        status.textContent =
          "No pudimos mostrar la figura. El código y el PDF se conservan; reintenta la vista previa.";
      }
    };
    const load = async (force: boolean) => {
      if (busy) return;
      busy = true;
      refresh.disabled = true;
      zoom.disabled = true;
      pdf.disabled = true;
      image.hidden = true;
      diagnostics.hidden = true;
      status.textContent = "Compilando esta figura con aislamiento…";
      try {
        const result = await studyRequest<Preview>(
          "/document-previews",
          this.context,
          { source, refresh: force },
          this.controller.signal,
        );
        if (!this.active || !panel.isConnected) return;
        confirmedMessage = result.message;
        status.textContent = result.message;
        if (result.state !== "ready" || !result.preview_id) {
          log.textContent = result.diagnostic || "";
          diagnostics.hidden = !result.diagnostic;
          return;
        }
        identifier = result.preview_id;
        const blob = await studyBinary(
          "/document-previews/" + identifier + "/png",
          this.context,
          undefined,
          this.controller.signal,
        );
        if (!this.active || !panel.isConnected) return;
        currentUrl = await pngDataUri(blob);
        if (!this.active || !panel.isConnected) return;
        status.textContent = "Mostrando la figura compilada…";
        image.src = currentUrl;
        image.hidden = false;
        pdf.disabled = false;
      } catch (error) {
        if (this.active && panel.isConnected)
          status.textContent = (error as Error).message;
      } finally {
        busy = false;
        refresh.disabled = false;
      }
    };
    refresh.onclick = () => void load(true);
    zoom.onclick = () => {
      const dialog = element("dialog");
      dialog.className = "figure-preview-dialog";
      const large = element("img");
      large.src = currentUrl;
      large.alt = image.alt;
      const close = element("button", "Cerrar figura");
      close.type = "button";
      close.onclick = () => dialog.close();
      dialog.addEventListener("close", () => {
        dialog.remove();
        this.dialogs.delete(dialog);
      });
      dialog.append(large, close);
      document.body.append(dialog);
      this.dialogs.add(dialog);
      dialog.showModal();
    };
    pdf.onclick = () =>
      void studyBinary(
        "/document-previews/" + identifier + "/pdf",
        this.context,
        undefined,
        this.controller.signal,
      )
        .then((blob) => {
          if (this.active) downloadDocument(blob, "mathmongo-figura.pdf");
        })
        .catch((error) => {
          if (this.active) status.textContent = error.message;
        });
    panel.append(status, image, refresh, zoom, pdf, diagnostics);
    host.append(panel);
    void load(false);
  };
  destroy() {
    this.active = false;
    this.controller.abort();
    this.dialogs.forEach((dialog) => dialog.remove());
    this.dialogs.clear();
  }
}
