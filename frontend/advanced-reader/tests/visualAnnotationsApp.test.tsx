import { act, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { AdvancedReaderApp } from "../src/app/App";
import type { AdvancedReaderApi } from "../src/api/client";
import {
  VISUAL_QUOTE_PREVIEW_CODE_POINTS,
  mergeVisualAnnotationSnapshots,
} from "../src/annotations/ui";
import type {
  CreateVisualAnnotation,
  VisualAnnotation,
} from "../src/types/api";
import {
  DOCUMENT_ID,
  FakePdfController,
  VERSION_ID,
  crossPageSelection,
  makeApi,
  metadata,
  samePageSelection,
} from "./fixtures";

const validSearch = `?document_id=${DOCUMENT_ID}`;
const readyMetadata = {
  ...metadata,
  capabilities: {
    ...metadata.capabilities,
    persistent_highlights: true,
    persistent_underlines: true,
    visual_annotation_editing: true,
    visual_annotation_archiving: true,
  },
};

function fromPayload(
  payload: CreateVisualAnnotation,
  overrides: Partial<VisualAnnotation> = {},
): VisualAnnotation {
  return {
    annotation_id: payload.annotation_id,
    document_id: DOCUMENT_ID,
    kind: payload.kind,
    status: "active",
    pdf_page: payload.pdf_page,
    page_label: "1",
    quote_text: payload.quote_text,
    body: payload.body,
    color_label: payload.color_label,
    tags: payload.tags,
    visual_status: "exact",
    visual_anchor: {
      version_id: payload.version_id,
      document_sha256: payload.document_sha256,
      coordinate_space: "normalized_unrotated_crop_box",
      capture_rotation: payload.capture_rotation,
      rects: payload.rects,
    },
    created_at: "2026-07-13T12:00:00Z",
    updated_at: "2026-07-13T12:00:00Z",
    archived_at: null,
    ...overrides,
  };
}

function visualApi(items: VisualAnnotation[] = []): AdvancedReaderApi {
  const api = makeApi({
    getMetadata: vi.fn().mockResolvedValue(readyMetadata),
    listVisualAnnotations: vi.fn().mockResolvedValue({
      items,
      page: 1,
      page_size: 100,
      total: items.length,
      pages: items.length > 0 ? 1 : 0,
    }),
  });
  api.createVisualAnnotation = vi.fn(async (_documentId, payload) => fromPayload(payload));
  api.updateVisualAnnotation = vi.fn(async (annotationId, patch) => {
    const index = items.findIndex((item) => item.annotation_id === annotationId);
    const current = items[index];
    if (current === undefined) throw new Error("missing fixture");
    const updated: VisualAnnotation = {
      ...current,
      ...patch,
      color_label: patch.color_label ?? current.color_label,
      updated_at: "2026-07-13T12:01:00Z",
    };
    items[index] = updated;
    return updated;
  });
  api.archiveVisualAnnotation = vi.fn(async (annotationId): Promise<VisualAnnotation> => {
    const index = items.findIndex((item) => item.annotation_id === annotationId);
    const current = items[index];
    if (current === undefined) throw new Error("missing fixture");
    const archived: VisualAnnotation = {
      ...current,
      status: "archived",
      archived_at: "2026-07-13T12:02:00Z",
    };
    items[index] = archived;
    return archived;
  });
  api.reactivateVisualAnnotation = vi.fn(async (annotationId): Promise<VisualAnnotation> => {
    const index = items.findIndex((item) => item.annotation_id === annotationId);
    const current = items[index];
    if (current === undefined) throw new Error("missing fixture");
    const active: VisualAnnotation = { ...current, status: "active", archived_at: null };
    items[index] = active;
    return active;
  });
  return api;
}

async function renderReady(api = visualApi(), controller = new FakePdfController()) {
  render(
    <AdvancedReaderApp
      api={api}
      controllerFactory={() => controller}
      search={validSearch}
    />,
  );
  await waitFor(() => expect(screen.getByLabelText("Página siguiente")).toBeEnabled());
  const page = document.createElement("div");
  page.className = "page";
  page.dataset.pageNumber = "3";
  Object.defineProperty(page, "getBoundingClientRect", {
    value: () => ({
      x: 100, y: 100, left: 100, top: 100, right: 700, bottom: 900,
      width: 600, height: 800, toJSON: () => ({}),
    }),
  });
  document.querySelector("#viewer")?.append(page);
  return { api, controller, user: userEvent.setup() };
}

describe("S5B visual annotation workflow", () => {
  it("does not let a stale active preload overwrite a newer archived response", () => {
    const payload: CreateVisualAnnotation = {
      annotation_id: "ann_123e4567-e89b-42d3-a456-426614174001",
      version_id: "dver_123e4567-e89b-42d3-a456-426614174099",
      document_sha256: "b".repeat(64),
      pdf_page: 1,
      kind: "highlight",
      quote_text: "A compact theorem",
      rects: [{ x: 0.1, y: 0.2, width: 0.4, height: 0.04 }],
      capture_rotation: 0,
      color_label: "yellow",
      body: "",
      tags: [],
    };
    const staleActive = fromPayload(payload, {
      updated_at: "2026-07-13T12:00:00Z",
    });
    const archived = fromPayload(payload, {
      status: "archived",
      updated_at: "2026-07-13T12:01:00Z",
      archived_at: "2026-07-13T12:01:00Z",
    });

    const afterLifecycle = mergeVisualAnnotationSnapshots(new Map(), [archived]);
    const afterLatePreload = mergeVisualAnnotationSnapshots(afterLifecycle, [staleActive]);

    expect(afterLatePreload.get(payload.annotation_id)).toEqual(archived);
  });

  it("shows the floating and inspector actions only for a valid single-page selection", async () => {
    const { controller } = await renderReady();
    act(() => controller.emitSelection(samePageSelection));
    expect(await screen.findByRole("toolbar", { name: "Guardar selección como marca visual" }))
      .toBeVisible();
    expect(screen.getAllByRole("button", { name: "Highlight" })).toHaveLength(2);

    act(() => controller.emitSelection(crossPageSelection));
    expect(screen.queryByRole("toolbar", { name: "Guardar selección como marca visual" }))
      .not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Highlight" })).not.toBeInTheDocument();

    act(() => controller.emitSelection({
      ...samePageSelection,
      pdf_page: null,
      rects_normalized: [],
      geometry_status: "unresolved",
    }));
    expect(screen.queryByRole("button", { name: "Underline" })).not.toBeInTheDocument();
  });

  it("requires confirmation and cancellation performs no write", async () => {
    const api = visualApi();
    const { controller, user } = await renderReady(api);
    act(() => controller.emitSelection(samePageSelection));
    const toolbar = await screen.findByRole("toolbar", {
      name: "Guardar selección como marca visual",
    });
    await user.click(within(toolbar).getByRole("button", { name: "Highlight" }));
    expect(screen.getByRole("heading", { name: "Guardar explícitamente" })).toBeVisible();
    expect(api.createVisualAnnotation).not.toHaveBeenCalled();
    await user.click(screen.getByRole("button", { name: "Cancelar" }));
    expect(api.createVisualAnnotation).not.toHaveBeenCalled();
  });

  it("creates one highlight after explicit save and preserves canonical geometry", async () => {
    const api = visualApi();
    const { controller, user } = await renderReady(api);
    act(() => controller.emitSelection(samePageSelection));
    const toolbar = await screen.findByRole("toolbar", {
      name: "Guardar selección como marca visual",
    });
    await user.selectOptions(within(toolbar).getByLabelText("Color de la marca"), "blue");
    await user.click(within(toolbar).getByRole("button", { name: "Highlight" }));
    await user.type(screen.getByLabelText("Comentario de la marca"), "Comentario local");
    await user.type(screen.getByLabelText("Tags de la marca"), "geometry, proof");
    await user.click(screen.getByRole("button", { name: "Guardar marca" }));

    await waitFor(() => expect(api.createVisualAnnotation).toHaveBeenCalledOnce());
    const [documentId, payload] = vi.mocked(api.createVisualAnnotation).mock.calls[0];
    expect(documentId).toBe(DOCUMENT_ID);
    expect(payload.annotation_id).toMatch(/^ann_[0-9a-f-]{36}$/u);
    expect(payload).toMatchObject({
      version_id: VERSION_ID,
      pdf_page: 3,
      kind: "highlight",
      color_label: "blue",
      body: "Comentario local",
      tags: ["geometry", "proof"],
      rects: samePageSelection.rects_normalized,
      capture_rotation: 0,
    });
    expect(controller.canonicalizeSelection).toHaveBeenCalledOnce();
    expect(controller.clearSelection).toHaveBeenCalledWith("user");
    expect(controller.setVisualAnnotations).toHaveBeenLastCalledWith([
      expect.objectContaining({ kind: "highlight", color_label: "blue" }),
    ]);
  });

  it("reuses the same annotation_id when an explicit save is retried", async () => {
    const api = visualApi();
    vi.mocked(api.createVisualAnnotation)
      .mockRejectedValueOnce(new Error("temporary"))
      .mockImplementationOnce(async (_documentId, payload) => fromPayload(payload));
    const { controller, user } = await renderReady(api);
    act(() => controller.emitSelection(samePageSelection));
    const toolbar = await screen.findByRole("toolbar", {
      name: "Guardar selección como marca visual",
    });
    await user.click(within(toolbar).getByRole("button", { name: "Underline" }));
    await user.click(screen.getByRole("button", { name: "Guardar marca" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("reintentar sin duplicarla");
    await user.click(screen.getByRole("button", { name: "Guardar marca" }));
    await waitFor(() => expect(api.createVisualAnnotation).toHaveBeenCalledTimes(2));
    const first = vi.mocked(api.createVisualAnnotation).mock.calls[0][1].annotation_id;
    const second = vi.mocked(api.createVisualAnnotation).mock.calls[1][1].annotation_id;
    expect(first).toBe(second);
  });

  it("filters, edits, archives, and reactivates through explicit API operations", async () => {
    const seedPayload: CreateVisualAnnotation = {
      annotation_id: "ann_123e4567-e89b-42d3-a456-426614174010",
      version_id: VERSION_ID,
      document_sha256: "a".repeat(64),
      pdf_page: 3,
      kind: "highlight",
      quote_text: "A compact theorem",
      rects: [{ x: 0.1, y: 0.2, width: 0.4, height: 0.04 }],
      capture_rotation: 0,
      color_label: "yellow",
      body: "old",
      tags: ["old"],
    };
    const seed = fromPayload(seedPayload);
    const api = visualApi([seed]);
    const { user } = await renderReady(api);
    expect(await screen.findByText("A compact theorem")).toBeVisible();
    await user.selectOptions(screen.getByLabelText("Tipo de anotaciones"), "highlight");
    await user.click(screen.getByRole("button", { name: "Editar" }));
    await user.selectOptions(screen.getByLabelText(`Editar tipo ${seed.annotation_id}`), "underline");
    await user.selectOptions(screen.getByLabelText(`Editar color ${seed.annotation_id}`), "pink");
    const comment = screen.getByLabelText(`Editar comentario ${seed.annotation_id}`);
    await user.clear(comment);
    await user.type(comment, "new comment");
    const tags = screen.getByLabelText(`Editar tags ${seed.annotation_id}`);
    await user.clear(tags);
    await user.type(tags, "one, two");
    await user.click(screen.getByRole("button", { name: "Guardar cambios" }));
    await waitFor(() => expect(api.updateVisualAnnotation).toHaveBeenCalledWith(
      seed.annotation_id,
      {
        kind: "underline",
        color_label: "pink",
        body: "new comment",
        tags: ["one", "two"],
      },
    ));
    expect(screen.queryByRole("button", { name: "Archivar" })).not.toBeInTheDocument();
    await user.selectOptions(screen.getByLabelText("Tipo de anotaciones"), "underline");
    await user.click(screen.getByRole("button", { name: "Archivar" }));
    await waitFor(() => expect(api.archiveVisualAnnotation).toHaveBeenCalledWith(seed.annotation_id));
    await user.selectOptions(screen.getByLabelText("Estado de anotaciones"), "archived");
    expect(await screen.findByRole("button", { name: "Reactivar" })).toBeVisible();
    await user.click(screen.getByRole("button", { name: "Reactivar" }));
    await waitFor(() => expect(api.reactivateVisualAnnotation).toHaveBeenCalledWith(seed.annotation_id));
  });

  it("shows mismatch, omits visual focus, and still navigates to the logical page", async () => {
    const payload: CreateVisualAnnotation = {
      annotation_id: "ann_123e4567-e89b-42d3-a456-426614174011",
      version_id: "dver_123e4567-e89b-42d3-a456-426614174099",
      document_sha256: "b".repeat(64),
      pdf_page: 7,
      kind: "underline",
      quote_text: "Historical version",
      rects: [{ x: 0.2, y: 0.3, width: 0.3, height: 0.03 }],
      capture_rotation: 90,
      color_label: "green",
      body: "",
      tags: [],
    };
    const mismatch = fromPayload(payload, { visual_status: "version_mismatch" });
    const api = visualApi([mismatch]);
    const { controller, user } = await renderReady(api);
    await user.selectOptions(screen.getByLabelText("Alcance de anotaciones"), "document");
    expect(await screen.findByText("Anotación visual asociada a otra versión del PDF.")).toBeVisible();
    await user.click(screen.getByRole("button", { name: "Ir a página" }));
    expect(controller.goToPage).toHaveBeenCalledWith(7, "pdfjs");
    expect(controller.focusVisualAnnotation).not.toHaveBeenCalled();
    expect(api.savePage).not.toHaveBeenCalled();
    expect(controller.setVisualAnnotations).toHaveBeenCalledWith([
      expect.objectContaining({ visual_status: "version_mismatch" }),
    ]);
  });

  it("focuses an exact active overlay and updates the page label without autosaving", async () => {
    const payload: CreateVisualAnnotation = {
      annotation_id: "ann_123e4567-e89b-42d3-a456-426614174012",
      version_id: VERSION_ID,
      document_sha256: "a".repeat(64),
      pdf_page: 7,
      kind: "highlight",
      quote_text: "Navigate to exact overlay",
      rects: [{ x: 0.15, y: 0.2, width: 0.35, height: 0.04 }],
      capture_rotation: 0,
      color_label: "purple",
      body: "",
      tags: [],
    };
    const exact = fromPayload(payload);
    const api = visualApi([exact]);
    const { controller, user } = await renderReady(api);
    await user.selectOptions(screen.getByLabelText("Alcance de anotaciones"), "document");
    expect(await screen.findByText("Navigate to exact overlay")).toBeVisible();
    expect(screen.getByText("purple · active")).toBeVisible();

    await user.click(screen.getByRole("button", { name: "Ir a página" }));

    expect(controller.focusVisualAnnotation).toHaveBeenCalledWith(exact.annotation_id);
    expect(await screen.findByText("Book page 5 · PDF page 7")).toBeVisible();
    expect(api.savePage).not.toHaveBeenCalled();
  });

  it("abbreviates sidebar quote previews by Unicode code point", async () => {
    const longQuote = `${"😀".repeat(VISUAL_QUOTE_PREVIEW_CODE_POINTS + 20)} final`;
    const payload: CreateVisualAnnotation = {
      annotation_id: "ann_123e4567-e89b-42d3-a456-426614174013",
      version_id: VERSION_ID,
      document_sha256: "a".repeat(64),
      pdf_page: 3,
      kind: "underline",
      quote_text: longQuote,
      rects: [{ x: 0.15, y: 0.2, width: 0.35, height: 0.04 }],
      capture_rotation: 0,
      color_label: "blue",
      body: "",
      tags: [],
    };
    const api = visualApi([fromPayload(payload)]);
    await renderReady(api);
    const preview = `${"😀".repeat(VISUAL_QUOTE_PREVIEW_CODE_POINTS - 1)}…`;

    expect(await screen.findByText(preview)).toBeVisible();
    expect(Array.from(preview)).toHaveLength(VISUAL_QUOTE_PREVIEW_CODE_POINTS);
    expect(screen.queryByText(longQuote)).not.toBeInTheDocument();
  });
});
