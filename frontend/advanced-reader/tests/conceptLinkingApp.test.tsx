import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { AdvancedReaderApp } from "../src/app/App";
import type {
  ConceptEvidence,
  ConceptSummary,
  DocumentConceptGroup,
  VisualAnnotation,
} from "../src/types/api";
import {
  DOCUMENT_ID,
  FakePdfController,
  VERSION_ID,
  makeApi,
  metadata,
} from "./fixtures";

const validSearch = `?document_id=${DOCUMENT_ID}`;
const annotationId = "ann_123e4567-e89b-42d3-a456-426614174021";
const evidenceId = "ev_123e4567-e89b-42d3-a456-426614174022";

const concept: ConceptSummary = {
  concept_legacy_id: "compactness",
  concept_legacy_source: "TopologyBook",
  title: "Compacidad",
  concept_type: "definition",
  categories: ["Topología"],
  tags: ["cover"],
  evidence_count: 2,
  evidence_in_document_count: 1,
  warning: null,
};

const annotation: VisualAnnotation = {
  annotation_id: annotationId,
  document_id: DOCUMENT_ID,
  kind: "highlight",
  status: "active",
  pdf_page: 3,
  page_label: "1",
  quote_text: "Toda cubierta abierta admite un subcubrimiento finito.",
  body: "Comentario de la marca",
  color_label: "yellow",
  tags: ["topology"],
  visual_status: "exact",
  visual_anchor: {
    version_id: VERSION_ID,
    document_sha256: "a".repeat(64),
    coordinate_space: "normalized_unrotated_crop_box",
    capture_rotation: 0,
    rects: [{ x: 0.1, y: 0.2, width: 0.4, height: 0.04 }],
  },
  created_at: "2026-07-15T12:00:00Z",
  updated_at: "2026-07-15T12:00:00Z",
  archived_at: null,
};

const evidence: ConceptEvidence = {
  evidence_link_id: evidenceId,
  concept,
  link_type: "definition_source",
  link_type_label: "Fuente de definición",
  comment: "Definición primaria",
  status: "active",
  created_at: "2026-07-15T12:00:00Z",
  updated_at: "2026-07-15T12:00:00Z",
  archived_at: null,
  annotation: {
    annotation_id: annotationId,
    kind: "highlight",
    status: "active",
    visual_status: "exact",
    pdf_page: 3,
    book_page_label: "1",
    quote_text: annotation.quote_text,
    color_label: "yellow",
    annotation_comment: annotation.body,
  },
};

function group(items: ConceptEvidence[] = [evidence]): DocumentConceptGroup {
  return {
    concept,
    highlight_count: items.length,
    underline_count: 0,
    pages: [3],
    link_types: ["definition_source"],
    evidence: items,
  };
}

function conceptApi(options: {
  visual?: VisualAnnotation;
  groups?: DocumentConceptGroup[];
  unlinked?: boolean;
} = {}) {
  const visual = options.visual ?? annotation;
  const groups = options.groups ?? [];
  const api = makeApi({
    getMetadata: vi.fn().mockResolvedValue({
      ...metadata,
      capabilities: {
        ...metadata.capabilities,
        persistent_highlights: true,
        persistent_underlines: true,
        visual_annotation_editing: true,
        visual_annotation_archiving: true,
        concept_search: true,
        annotation_concept_links: true,
        concept_link_archive: true,
        concept_link_reactivate: true,
        concept_linking: true,
      },
    }),
    listVisualAnnotations: vi.fn().mockResolvedValue({
      items: [visual], page: 1, page_size: 100, total: 1, pages: 1,
    }),
    getVisualAnnotation: vi.fn().mockResolvedValue(visual),
    searchConcepts: vi.fn().mockResolvedValue({
      items: [concept], page: 1, page_size: 20, has_more: false,
    }),
    listDocumentConceptEvidence: vi.fn().mockResolvedValue({
      items: groups, page: 1, page_size: 50, total: groups.length, pages: groups.length ? 1 : 0,
    }),
    listUnlinkedVisualAnnotations: vi.fn().mockResolvedValue({
      items: options.unlinked ? [{
        annotation_id: annotationId,
        kind: "highlight",
        pdf_page: 3,
        book_page_label: "1",
        quote_text: annotation.quote_text,
        color_label: "yellow",
      }] : [],
      page: 1,
      page_size: 50,
      total: options.unlinked ? 1 : 0,
      pages: options.unlinked ? 1 : 0,
    }),
  });
  api.createAnnotationConceptEvidence = vi.fn().mockResolvedValue({
    result: "success",
    item: evidence,
  });
  api.archiveConceptEvidence = vi.fn().mockResolvedValue({
    result: "success", item: { ...evidence, status: "archived" },
  });
  api.reactivateConceptEvidence = vi.fn().mockResolvedValue({ result: "success", item: evidence });
  return api;
}

async function renderReady(api = conceptApi(), controller = new FakePdfController()) {
  render(
    <AdvancedReaderApp
      api={api}
      controllerFactory={() => controller}
      search={validSearch}
    />,
  );
  await waitFor(() => expect(screen.getByLabelText("Página siguiente")).toBeEnabled());
  return { api, controller, user: userEvent.setup() };
}

describe("S5C guided visual concept linking", () => {
  it("opens explicitly, searches cards, confirms context, and saves once", async () => {
    const api = conceptApi({ unlinked: true });
    const { user } = await renderReady(api);
    await user.click(screen.getByRole("button", { name: "Revisar marcas" }));
    const visualCard = document.querySelector(`[data-annotation-id="${annotationId}"]`);
    expect(visualCard).not.toBeNull();
    await user.click(within(visualCard as HTMLElement).getByRole("button", { name: "Asociar concepto" }));

    expect(screen.getByRole("heading", { name: "Asociar concepto" })).toBeVisible();
    expect(screen.queryByLabelText("Pasos de asociación")).not.toBeInTheDocument();
    await user.type(screen.getByLabelText("Buscar concepto"), "Compacidad");
    await user.click(screen.getByRole("button", { name: "Buscar" }));
    expect(await screen.findByRole("heading", { name: "Compacidad" })).toBeVisible();
    await user.click(screen.getByRole("button", { name: "Seleccionar" }));
    await user.click(screen.getByRole("button", { name: "Cambiar" }));
    await user.selectOptions(screen.getByLabelText("Tipo de evidencia"), "definition_source");
    await user.type(screen.getByLabelText("Comentario del vínculo"), "Definición primaria");
    expect(screen.getByText("Fuente de definición")).toBeVisible();
    expect(screen.getAllByText(annotation.quote_text).length).toBeGreaterThan(0);
    await user.click(screen.getByRole("button", { name: "Guardar" }));
    await waitFor(() => expect(api.createAnnotationConceptEvidence).toHaveBeenCalledOnce());
    expect(vi.mocked(api.createAnnotationConceptEvidence).mock.calls[0][1]).toMatchObject({
      concept_legacy_id: "compactness",
      concept_legacy_source: "TopologyBook",
      link_type: "definition_source",
      comment: "Definición primaria",
    });
    expect(vi.mocked(api.createAnnotationConceptEvidence).mock.calls[0][1].evidence_link_id)
      .toMatch(/^ev_[0-9a-f-]{36}$/u);
    expect(screen.getByLabelText("Documento PDF")).toBeVisible();
  });

  it("keeps the evidence id and draft after a partial network failure", async () => {
    const api = conceptApi();
    vi.mocked(api.createAnnotationConceptEvidence)
      .mockRejectedValueOnce(new Error("connection lost after write"))
      .mockResolvedValueOnce({ result: "identical", item: evidence });
    const { user } = await renderReady(api);
    await user.click(screen.getByRole("button", { name: "Revisar marcas" }));
    const visualCard = document.querySelector(`[data-annotation-id="${annotationId}"]`) as HTMLElement;
    await user.click(within(visualCard).getByRole("button", { name: "Asociar concepto" }));
    await user.type(screen.getByLabelText("Buscar concepto"), "Compacidad");
    await user.click(screen.getByRole("button", { name: "Buscar" }));
    await user.click(await screen.findByRole("button", { name: "Seleccionar" }));
    await user.click(screen.getByRole("button", { name: "Guardar" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("reintentar sin duplicarlo");
    await user.click(screen.getByRole("button", { name: "Reintentar" }));
    await waitFor(() => expect(api.createAnnotationConceptEvidence).toHaveBeenCalledTimes(2));
    const calls = vi.mocked(api.createAnnotationConceptEvidence).mock.calls;
    expect(calls[0][1].evidence_link_id).toBe(calls[1][1].evidence_link_id);
  });

  it("shows annotation, page, document, unlinked, and lifecycle cards", async () => {
    const api = conceptApi({ groups: [group()], unlinked: true });
    const { controller, user } = await renderReady(api);
    await user.click(screen.getByRole("button", { name: "Revisar marcas" }));
    expect(screen.getByRole("heading", { name: "Conceptos asociados" })).toBeVisible();
    expect(screen.getAllByText("Compacidad").length).toBeGreaterThan(0);

    const associated = screen.getByLabelText("Conceptos asociados");
    await user.click(within(associated).getByRole("button", { name: "Archivar vínculo" }));
    await waitFor(() => expect(api.archiveConceptEvidence).toHaveBeenCalledWith(evidenceId));
    await user.click(within(associated).getByRole("button", { name: "Ir a la marca" }));
    expect(controller.focusVisualAnnotation).toHaveBeenCalledWith(annotationId);
    await user.click(screen.getByRole("button", { name: "Conocimiento" }));
    expect(await screen.findByRole("heading", { name: "Conceptos en esta página" })).toBeVisible();
    expect(screen.getByRole("heading", { name: "Conceptos del documento" })).toBeVisible();
    expect(screen.getByRole("heading", { name: "Marcas sin concepto" })).toBeVisible();
  });

  it("does not offer new linking for archived or version-mismatched annotations", async () => {
    const mismatch = { ...annotation, visual_status: "version_mismatch" as const };
    const { user } = await renderReady(conceptApi({ visual: mismatch, groups: [group()] }));
    await user.click(screen.getByRole("button", { name: "Revisar marcas" }));
    const visualCard = document.querySelector(`[data-annotation-id="${annotationId}"]`) as HTMLElement;
    expect(within(visualCard).queryByRole("button", { name: "Asociar concepto" }))
      .not.toBeInTheDocument();
    expect(within(visualCard).getByText(/otra versión/u)).toBeVisible();
    expect(within(visualCard).getByText("Compacidad")).toBeVisible();
  });

  it("keeps archived annotation links visible and blocks link reactivation", async () => {
    const archivedAnnotation = {
      ...annotation,
      status: "archived" as const,
      archived_at: "2026-07-15T13:00:00Z",
    };
    const archivedEvidence: ConceptEvidence = {
      ...evidence,
      status: "archived",
      archived_at: "2026-07-15T13:00:00Z",
      annotation: evidence.annotation === null ? null : {
        ...evidence.annotation,
        status: "archived",
      },
    };
    const api = conceptApi({ visual: archivedAnnotation, groups: [group([archivedEvidence])] });
    const { user } = await renderReady(api);
    await user.click(screen.getByRole("button", { name: "Revisar marcas" }));
    await user.selectOptions(screen.getByLabelText("Estado de anotaciones"), "archived");
    await waitFor(() => expect(document.querySelector(
      `[data-annotation-id="${annotationId}"]`,
    )).not.toBeNull());

    const visualCard = document.querySelector(`[data-annotation-id="${annotationId}"]`) as HTMLElement;
    expect(within(visualCard).getByText("Compacidad")).toBeVisible();
    expect(within(visualCard).getByText(/Reactiva primero la marca visual/u)).toBeVisible();
    expect(within(visualCard).queryByRole("button", { name: "Reactivar vínculo" }))
      .not.toBeInTheDocument();
    expect(api.reactivateConceptEvidence).not.toHaveBeenCalled();
  });

  it("does not write when the wizard is cancelled", async () => {
    const api = conceptApi();
    const { user } = await renderReady(api);
    await user.click(screen.getByRole("button", { name: "Revisar marcas" }));
    const visualCard = document.querySelector(`[data-annotation-id="${annotationId}"]`) as HTMLElement;
    await user.click(within(visualCard).getByRole("button", { name: "Asociar concepto" }));
    await user.click(screen.getByRole("button", { name: "Cancelar" }));
    expect(api.createAnnotationConceptEvidence).not.toHaveBeenCalled();
  });
});
