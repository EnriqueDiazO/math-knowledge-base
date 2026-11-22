/** Own the document dialog lifetime independently of the spherical map. */
import { element, button, field, selector } from "./ui";
import type { Data, Draft, View } from "./model";
import { intention } from "./model";
import { DocumentEditor } from "./document-editor";
import { DocumentCitation } from "./document-citation";
import { renderConceptSources } from "./provenance";
import type { DraftVault } from "./drafts";
type Options = {
  view: View;
  data: Data;
  vault: DraftVault;
  root: HTMLElement;
  canvas: HTMLCanvasElement;
  save: () => void;
  refresh: () => void;
  renderStatus: () => void;
  submitPending: () => void;
  requestDraw: () => void;
  onExit?: () => void;
  setTriggerValue: (key: string, value: unknown) => void;
};
export class DocumentDialog {
  private composer?: DocumentEditor;
  private citationControls?: DocumentCitation;
  private dialog?: HTMLDialogElement;
  constructor(private options: Options) {}
  close(): void {
    const { view, vault, save } = this.options;
    this.citationControls?.destroy();
    this.citationControls = undefined;
    if (view.draft && this.composer) {
      view.draft.content = this.composer.value();
      view.draft.document = this.composer.snapshot();
      vault.put(view.draft);
    }
    this.composer?.destroy();
    this.composer = undefined;
    this.dialog?.remove();
    this.dialog = undefined;
    save();
  }
  private keepAndClose = (): void => {
    const { view, refresh, canvas, onExit } = this.options;
    this.close();
    view.draft = undefined;
    view.status = {
      status: "draft",
      message:
        "Borrador local conservado. Puedes recuperarlo; no se publicó contenido nuevo.",
    };
    refresh();
    canvas.focus();
    onExit?.();
  };
  open(): void {
    const {
      view,
      data,
      vault,
      save,
      refresh,
      root,
      onExit,
      setTriggerValue,
      submitPending,
      renderStatus,
    } = this.options;
    if (!view.draft) return;
    const draft = view.draft;
    this.citationControls?.destroy();
    this.dialog?.remove();
    this.composer?.destroy();
    const dialog = element("dialog", "", "document-dialog editor-dialog");
    this.dialog = dialog;
    const header = element("header");
    header.append(
      element(
        "h2",
        draft.action === "save_note"
          ? "Escribir nota de trabajo"
          : draft.action === "edit"
            ? "Editar concepto"
            : draft.action === "connect"
              ? "Conectar conceptos"
              : "Escribir concepto",
      ),
    );
    const close = button(
      "Conservar borrador y volver",
      this.keepAndClose,
      header,
    );
    close.disabled = !!view.pending;
    if (view.pending) {
      header.append(
        element(
          "p",
          "Envío sin confirmar. El borrador permanece intacto; reconcilia el mismo intento.",
        ),
      );
      button("Reconciliar envío del documento", submitPending, header, true);
      button(
        "Volver conservando el envío pendiente",
        () => {
          this.close();
          refresh();
          onExit?.();
        },
        header,
      );
    }
    dialog.append(header);
    const form = element("form");
    form.inert = !!view.pending;
    dialog.append(form);
    const meta = element("details");
    meta.open = draft.action === "connect";
    meta.append(element("summary", "Metadatos, fuente y referencia"));
    form.append(meta);
    const name = field(form, "Nombre", draft.title, (value) => {
      draft.title = value;
      vault.put(draft);
    });
    name.required = draft.action !== "connect";
    name.maxLength = 500;
    if (
      !["edit", "connect", "publish_note"].includes(draft.action) &&
      !(draft.action === "save_note" && (draft.documentId || draft.noteId))
    )
      selector(
        meta,
        "Source administrada",
        data.sources.map((s) => ({ value: s.id, text: s.name })),
        draft.source,
        (value) => {
          draft.source = value;
          save();
        },
      );
    if (!["edit", "connect", "save_note"].includes(draft.action))
      selector(
        meta,
        "Tipo de concepto",
        data.concept_types.map((s) => ({ value: s, text: s })),
        draft.type,
        (value) => {
          draft.type = value;
          save();
        },
      );
    if (draft.action !== "save_note") {
      field(
        meta,
        "Categorías separadas por comas",
        draft.categories,
        (value) => {
          draft.categories = value;
          save();
        },
      );
      field(
        meta,
        "Comentario",
        draft.comment,
        (value) => {
          draft.comment = value;
          save();
        },
        true,
      );
    }
    if (draft.action === "edit") {
      const node = data.nodes.find((n) => n.key === draft.origin);
      if (node) renderConceptSources(meta, node, data, setTriggerValue);
    }
    if (draft.action !== "connect")
      this.citationControls = new DocumentCitation(
        dialog,
        form,
        draft,
        () => vault.put(draft),
        (payload) => setTriggerValue("bibliography", payload),
        () => this.composer?.restoreFocus(),
      );
    if (draft.action !== "connect") {
      const writing = element("div");
      form.append(writing);
      this.composer = new DocumentEditor(
        writing,
        draft.content,
        (content, snapshot) => {
          draft.content = content;
          draft.document = snapshot;
          vault.put(draft);
        },
        draft.document,
      );
    }
    if (["connect", "create_connected"].includes(draft.action))
      this.relationFields(form, draft);
    const controls = element("div", "", "editor-actions");
    form.append(controls);
    const submit = element(
      "button",
      draft.action === "save_note" ? "Guardar nota" : "Guardar concepto",
      "primary",
    );
    submit.type = "submit";
    submit.disabled =
      !!view.pending ||
      (draft.action.startsWith("create") && !data.sources.length);
    controls.append(submit);
    button(
      "Descargar borrador",
      () => {
        const url = URL.createObjectURL(
          new Blob([JSON.stringify(draft, null, 2)], {
            type: "application/json",
          }),
        );
        const link = element("a");
        link.href = url;
        link.download = "mathmongo-borrador.json";
        link.click();
        URL.revokeObjectURL(url);
      },
      controls,
    );
    if (!view.pending)
      button(
        "Descartar borrador…",
        () => {
          const confirmation = element("div", "", "discard-confirm");
          confirmation.append(
            element(
              "p",
              "¿Descartar este borrador local? Los conceptos ya guardados permanecerán.",
            ),
          );
          button(
            "Sí, descartar este borrador",
            () => {
              const id = draft.id!;
              this.composer?.destroy();
              this.composer = undefined;
              view.draft = undefined;
              vault.discard(id);
              dialog.remove();
              this.dialog = undefined;
              refresh();
            },
            confirmation,
          );
          button(
            "Seguir escribiendo",
            () => confirmation.remove(),
            confirmation,
          );
          controls.append(confirmation);
        },
        controls,
      );
    if (
      view.status?.status === "conflict" &&
      ["edit", "save_note", "publish_note"].includes(draft.action)
    )
      button(
        "Revisar versión actual",
        () => {
          const note = data.notes?.find((n) => n.note_id === draft.noteId);
          const node =
            draft.action === "edit"
              ? data.nodes.find((n) => n.key === draft.origin)
              : note
                ? {
                    titulo: note.title,
                    contenido_latex: note.body,
                    revision: note.revision,
                  }
                : undefined;
          if (!node) return;
          const review = element("section");
          review.append(
            element("p", `Versión actual de ${node.titulo}`),
            element("pre", node.contenido_latex),
          );
          button(
            "He revisado: usar esta versión como base",
            () => {
              draft.revision = node.revision;
              if (draft.action === "publish_note")
                draft.noteRevision = node.revision;
              view.status = {
                status: "draft",
                message:
                  "Revisión actual adoptada explícitamente; borrador conservado.",
              };
              vault.put(draft);
              review.remove();
              renderStatus();
            },
            review,
          );
          controls.append(review);
        },
        controls,
      );
    form.onsubmit = (event) => {
      event.preventDefault();
      if (view.pending) return;
      if (this.composer && !this.composer.valid()) {
        view.status = {
          status: "draft",
          message:
            "Hay una fórmula en elaboración. El borrador está conservado; corrígela antes de confirmar.",
        };
        renderStatus();
        return;
      }
      draft.content = this.composer?.value() ?? draft.content;
      draft.submitted = true;
      vault.put(draft);
      view.pending = intention(draft, crypto.randomUUID());
      form.inert = true;
      submitPending();
    };
    if (view.pending)
      form
        .querySelectorAll("input,select,textarea,button")
        .forEach((n) => ((n as HTMLInputElement).disabled = true));
    dialog.oncancel = (event) => {
      event.preventDefault();
      if (!view.pending) this.keepAndClose();
    };
    root.append(dialog);
    dialog.showModal();
    this.composer?.restoreViewport();
    if (draft.document && !draft.bibliography?.open && !view.pending)
      this.composer?.restoreFocus();
    this.citationControls?.restore();
  }
  private relationFields(parent: HTMLElement, draft: Draft): void {
    const { data, save, requestDraw } = this.options;
    const preview = element("p", "", "preview");
    const update = () => {
      const origin =
          data.nodes.find((n) => n.key === draft.origin)?.titulo ??
          draft.origin,
        target =
          draft.action === "connect"
            ? (data.nodes.find((n) => n.key === draft.target)?.titulo ??
              "Destino")
            : draft.title;
      preview.textContent = `${draft.reverse ? target : origin} → [${draft.relation}] → ${draft.reverse ? origin : target}`;
      save();
      requestDraw();
    };
    if (draft.action === "connect")
      selector(
        parent,
        "Destino",
        [
          { value: "", text: "Elegir concepto" },
          ...data.nodes.map((n) => ({
            value: n.key,
            text: `${n.titulo} · ${n.source}`,
          })),
        ],
        draft.target,
        (v) => {
          draft.target = v;
          update();
        },
      );
    selector(
      parent,
      "Tipo de relación",
      data.relation_types.map((s) => ({ value: s, text: s })),
      draft.relation,
      (v) => {
        draft.relation = v;
        update();
      },
    );
    const label = element("label", "Invertir sentido "),
      checkbox = element("input");
    checkbox.type = "checkbox";
    checkbox.checked = draft.reverse;
    checkbox.onchange = () => {
      draft.reverse = checkbox.checked;
      update();
    };
    label.append(checkbox);
    parent.append(label, preview);
    update();
  }
}
