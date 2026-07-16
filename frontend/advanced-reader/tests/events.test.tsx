import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { ReaderApiError } from "../src/api/client";
import { AdvancedReaderApp } from "../src/app/App";
import type { AdvancedReaderEventV1 } from "../src/types/events";
import {
  DOCUMENT_ID,
  FakePdfController,
  VERSION_ID,
  makeApi,
  metadata,
  samePageSelection,
} from "./fixtures";

const validSearch = `?document_id=${DOCUMENT_ID}`;

function assertNever(value: never): never {
  throw new Error(`Unexpected event: ${String(value)}`);
}

function eventName(event: AdvancedReaderEventV1): AdvancedReaderEventV1["event_type"] {
  switch (event.event_type) {
    case "document_loaded":
    case "document_load_failed":
    case "page_changed":
    case "zoom_changed":
    case "rotation_changed":
    case "search_started":
    case "search_result":
    case "text_selection":
    case "selection_cleared":
    case "reading_position_saved":
      return event.event_type;
    default:
      return assertNever(event);
  }
}

function emittedEvents(observer: ReturnType<typeof vi.fn>): AdvancedReaderEventV1[] {
  return observer.mock.calls.map(([event]) => event as AdvancedReaderEventV1);
}

async function renderWithEvents(
  observer = vi.fn<(event: AdvancedReaderEventV1) => void>(),
  controller = new FakePdfController(),
) {
  const api = makeApi();
  render(
    <AdvancedReaderApp
      api={api}
      controllerFactory={() => controller}
      search={validSearch}
      onEvent={observer}
    />,
  );
  await waitFor(() =>
    expect(observer).toHaveBeenCalledWith(
      expect.objectContaining({ event_type: "document_loaded" }),
    ));
  return { api, controller, observer, user: userEvent.setup() };
}

describe("AdvancedReaderEventV1 local event contract", () => {
  it("emits bounded load, page and zoom events after PDF.js is ready", async () => {
    const { observer } = await renderWithEvents();
    const events = emittedEvents(observer);

    expect(events.slice(0, 3).map(eventName)).toEqual([
      "document_loaded",
      "page_changed",
      "zoom_changed",
    ]);
    expect(events[0]).toEqual({
      schema_version: 1,
      event_type: "document_loaded",
      document_id: DOCUMENT_ID,
      version_id: VERSION_ID,
      total_pages: 12,
      initial_pdf_page: 3,
    });
    expect(events[1]).toEqual(expect.objectContaining({
      pdf_page: 3,
      total_pages: 12,
      book_page_label: "1",
      origin: "initial",
    }));
    expect(events[2]).toEqual(expect.objectContaining({
      scale: 1,
      mode: "fit_width",
    }));
  });

  it("caps search by Unicode code point and emits no query in result events", async () => {
    const { controller, observer } = await renderWithEvents();
    observer.mockClear();
    const input = screen.getByLabelText("Buscar en el PDF");
    fireEvent.change(input, { target: { value: "😀".repeat(300) } });
    fireEvent.keyDown(input, { key: "Enter" });

    const [query] = controller.search.mock.calls.at(-1) ?? [];
    expect(Array.from(query ?? "")).toHaveLength(256);
    const started = emittedEvents(observer).find(
      (event) => event.event_type === "search_started",
    );
    expect(started).toEqual(expect.objectContaining({
      query,
      case_sensitive: false,
      whole_words: false,
      direction: "next",
    }));

    act(() => controller.emitSearch({ status: "found", current: 2, total: 8 }));
    const result = emittedEvents(observer).at(-1);
    expect(result).toEqual(expect.objectContaining({
      event_type: "search_result",
      status: "found",
      current_match: 2,
      total_matches: 8,
    }));
    expect(result).not.toHaveProperty("query");
  });

  it("exposes only finite zoom values inside the 0.25..5 contract", async () => {
    const { controller, observer } = await renderWithEvents();
    observer.mockClear();

    act(() => controller.options?.handlers.onZoomChanged(99));

    expect(screen.getByLabelText("Zoom actual")).toHaveTextContent("500%");
    expect(emittedEvents(observer)).toEqual([expect.objectContaining({
      event_type: "zoom_changed",
      scale: 5,
      mode: "fit_width",
    })]);
  });

  it("clears ephemeral selection before emitting a rotation", async () => {
    const { controller, observer, user } = await renderWithEvents();
    act(() => controller.emitSelection(samePageSelection));
    expect(emittedEvents(observer).at(-1)).toEqual(samePageSelection);
    observer.mockClear();

    await user.click(screen.getByLabelText("Rotar a la derecha"));

    expect(emittedEvents(observer).map(eventName)).toEqual([
      "selection_cleared",
      "rotation_changed",
    ]);
    expect(emittedEvents(observer)[0]).toEqual(expect.objectContaining({
      reason: "rotation_change",
    }));
    expect(emittedEvents(observer)[1]).toEqual(expect.objectContaining({
      rotation: 90,
      direction: "clockwise",
    }));
    expect(screen.getByRole("heading", { name: "Book page 1 · PDF page 3" })).toBeVisible();
  });

  it("emits reading_position_saved only after the explicit successful PUT", async () => {
    const { api, observer, user } = await renderWithEvents();
    expect(emittedEvents(observer).some(
      (event) => event.event_type === "reading_position_saved",
    )).toBe(false);

    await user.click(screen.getByRole("button", { name: "Guardar posición" }));
    await screen.findByText("Posición guardada.");

    expect(api.savePage).toHaveBeenCalledWith(DOCUMENT_ID, 3);
    expect(emittedEvents(observer).at(-1)).toEqual({
      schema_version: 1,
      event_type: "reading_position_saved",
      document_id: DOCUMENT_ID,
      version_id: VERSION_ID,
      pdf_page: 3,
      reading_status: "in_progress",
    });
  });

  it("emits only a public error code when metadata loading fails", async () => {
    const observer = vi.fn<(event: AdvancedReaderEventV1) => void>();
    const api = makeApi({
      getMetadata: vi.fn().mockRejectedValue(
        new ReaderApiError("integrity_error", "/home/private/raw failure", 409),
      ),
    });
    render(
      <AdvancedReaderApp
        api={api}
        controllerFactory={() => new FakePdfController()}
        search={validSearch}
        onEvent={observer}
      />,
    );

    await screen.findByRole("alert");
    expect(emittedEvents(observer)).toEqual([{
      schema_version: 1,
      event_type: "document_load_failed",
      document_id: DOCUMENT_ID,
      version_id: null,
      error_code: "integrity_error",
    }]);
    expect(JSON.stringify(emittedEvents(observer))).not.toContain("/home/private");
  });

  it("requires the current page to paint even when an adjacent prefetched page succeeds", async () => {
    const observer = vi.fn<(event: AdvancedReaderEventV1) => void>();
    const controller = new FakePdfController(false);
    const { user } = await renderWithEvents(observer, controller);

    expect(document.querySelector(".reader-app")).toHaveAttribute("data-phase", "loading_pdf");
    expect(screen.getByLabelText("Página siguiente")).toBeDisabled();

    act(() => controller.options?.handlers.onPageRenderFailed(4));
    expect(document.querySelector(".reader-app")).toHaveAttribute("data-phase", "loading_pdf");
    expect(
      emittedEvents(observer).filter(
        (event) =>
          event.event_type === "document_load_failed" &&
          event.error_code === "page_render_failed",
      ),
    ).toHaveLength(0);

    act(() => controller.options?.handlers.onPageRendered(4));
    expect(document.querySelector(".reader-app")).toHaveAttribute("data-phase", "loading_pdf");
    expect(screen.queryByText("No se pudo renderizar PDF page 4.")).not.toBeInTheDocument();

    act(() => controller.options?.handlers.onPageRenderFailed(3));

    expect(document.querySelector(".reader-app")).toHaveAttribute(
      "data-phase",
      "page_render_failed",
    );
    expect(screen.getByRole("alert")).toHaveAttribute("data-error-code", "page_render_failed");
    expect(screen.getByText("El lector no ocultará una página en blanco.")).toBeVisible();
    expect(screen.getByLabelText("Página siguiente")).toBeEnabled();
    expect(
      emittedEvents(observer).filter(
        (event) =>
          event.event_type === "document_load_failed" &&
          event.error_code === "page_render_failed",
      ),
    ).toHaveLength(1);

    await user.click(screen.getByRole("button", { name: "Reintentar página" }));
    expect(controller.retryPage).toHaveBeenCalledWith(3);
    await waitFor(() =>
      expect(document.querySelector(".reader-app")).toHaveAttribute("data-phase", "ready"),
    );
    expect(screen.queryByText("El lector no ocultará una página en blanco.")).not.toBeInTheDocument();
  });

  it("uses metadata capabilities to disable unsupported toolbar operations", async () => {
    const observer = vi.fn<(event: AdvancedReaderEventV1) => void>();
    const restrictedMetadata = {
      ...metadata,
      capabilities: {
        ...metadata.capabilities,
        page_navigation: false,
        thumbnails: false,
        zoom: false,
        rotate: false,
        text_search: false,
      },
    };
    const api = makeApi({ getMetadata: vi.fn().mockResolvedValue(restrictedMetadata) });
    render(
      <AdvancedReaderApp
        api={api}
        controllerFactory={() => new FakePdfController()}
        search={validSearch}
        onEvent={observer}
      />,
    );
    await waitFor(() =>
      expect(observer).toHaveBeenCalledWith(
        expect.objectContaining({ event_type: "document_loaded" }),
      ));

    expect(screen.getByLabelText("Mostrar u ocultar miniaturas")).toBeDisabled();
    expect(screen.getByLabelText("Miniaturas PDF")).toHaveAttribute("aria-hidden", "true");
    expect(screen.getByLabelText("Página siguiente")).toBeDisabled();
    expect(screen.getByLabelText("PDF page")).toBeDisabled();
    expect(screen.getByLabelText("Aumentar zoom")).toBeDisabled();
    expect(screen.getByLabelText("Rotar a la derecha")).toBeDisabled();
    expect(screen.getByLabelText("Buscar en el PDF")).toBeDisabled();
  });
});
