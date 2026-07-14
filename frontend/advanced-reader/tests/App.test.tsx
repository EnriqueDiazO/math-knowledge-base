import { act, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { ReaderApiError } from "../src/api/client";
import { AdvancedReaderApp } from "../src/app/App";
import type { AdvancedReaderApi } from "../src/api/client";
import {
  DOCUMENT_ID,
  FakePdfController,
  crossPageSelection,
  makeApi,
  metadata,
  samePageSelection,
} from "./fixtures";

const validSearch = `?document_id=${DOCUMENT_ID}`;

async function renderReady(
  api: AdvancedReaderApi = makeApi(),
  controller = new FakePdfController(),
) {
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

describe("S5A frontend requirements 35-57", () => {
  it("[35] renders a bounded loading state", () => {
    const api = makeApi({ getMetadata: vi.fn(() => new Promise<never>(() => undefined)) });
    render(
      <AdvancedReaderApp api={api} controllerFactory={() => new FakePdfController()} search={validSearch} />,
    );
    expect(screen.getByRole("status")).toHaveTextContent("Preparando el lector");
    expect(screen.getByText(/Validando el Document/)).toBeVisible();
  });

  it("[36] renders a typed error state instead of an empty screen", async () => {
    const api = makeApi({
      getMetadata: vi.fn().mockRejectedValue(
        new ReaderApiError("integrity_error", "unsafe internal detail", 409),
      ),
    });
    render(
      <AdvancedReaderApp api={api} controllerFactory={() => new FakePdfController()} search={validSearch} />,
    );
    expect(await screen.findByRole("alert")).toHaveTextContent("No se pudo verificar el PDF");
    expect(screen.queryByText("unsafe internal detail")).not.toBeInTheDocument();
  });

  it("[37] renders the complete accessible toolbar", async () => {
    await renderReady();
    const toolbar = screen.getByRole("banner", { name: "Controles del lector PDF" });
    expect(within(toolbar).getByLabelText("Página anterior")).toBeVisible();
    expect(within(toolbar).getByLabelText("Aumentar zoom")).toBeVisible();
    expect(within(toolbar).getByRole("search")).toBeVisible();
    expect(within(toolbar).getByRole("button", { name: "Guardar posición" })).toBeVisible();
  });

  it("[38] shows the real total page count reported by the controller", async () => {
    await renderReady();
    expect(screen.getByLabelText("Total de páginas: 12")).toHaveTextContent("12");
    expect(screen.getByText("Pages").parentElement).toHaveTextContent("12");
  });

  it("[39] delegates previous and next navigation", async () => {
    const { controller, user } = await renderReady();
    await user.click(screen.getByLabelText("Página siguiente"));
    expect(controller.nextPage).toHaveBeenCalledOnce();
    expect(screen.getByLabelText("PDF page")).toHaveValue("4");
    await user.click(screen.getByLabelText("Página anterior"));
    expect(controller.previousPage).toHaveBeenCalledOnce();
    expect(screen.getByLabelText("PDF page")).toHaveValue("3");
  });

  it("[40] delegates first and last page navigation", async () => {
    const { controller, user } = await renderReady();
    await user.click(screen.getByLabelText("Última página"));
    expect(controller.goToPage).toHaveBeenCalledWith(12, "toolbar");
    await user.click(screen.getByLabelText("Primera página"));
    expect(controller.goToPage).toHaveBeenCalledWith(1, "toolbar");
  });

  it("[41] accepts a numeric page input", async () => {
    const { controller, user } = await renderReady();
    const input = screen.getByLabelText("PDF page");
    await user.clear(input);
    await user.type(input, "8{Enter}");
    expect(controller.goToPage).toHaveBeenCalledWith(8, "page_input");
    expect(input).toHaveValue("8");
  });

  it("[42] clamps page bounds and disables impossible navigation", async () => {
    const { controller, user } = await renderReady();
    const input = screen.getByLabelText("PDF page");
    await user.clear(input);
    await user.type(input, "999{Enter}");
    expect(input).toHaveValue("12");
    expect(screen.getByLabelText("Página siguiente")).toBeDisabled();
    act(() => controller.goToPage(1));
    expect(screen.getByLabelText("Página anterior")).toBeDisabled();
  });

  it("[43] a thumbnail selection navigates through the controller", async () => {
    const { controller, user } = await renderReady();
    await user.click(screen.getByLabelText("Ir a PDF page 7"));
    expect(controller.goToPage).toHaveBeenCalledWith(7, "thumbnail");
    expect(screen.getByLabelText("PDF page")).toHaveValue("7");
  });

  it("[44] toggles the thumbnail sidebar without removing the PDF", async () => {
    const { user } = await renderReady();
    const sidebar = screen.getByLabelText("Miniaturas PDF");
    await user.click(screen.getByLabelText("Mostrar u ocultar miniaturas"));
    expect(sidebar).toHaveAttribute("aria-hidden", "true");
    expect(screen.getByLabelText("Documento PDF")).toBeInTheDocument();
  });

  it("[45] toggles the inspector", async () => {
    const { user } = await renderReady();
    const inspector = screen.getByLabelText("Inspector");
    await user.click(screen.getByLabelText("Mostrar u ocultar inspector"));
    expect(inspector).toHaveAttribute("aria-hidden", "true");
  });

  it("[46] zooms in and out and reports the percentage", async () => {
    const { controller, user } = await renderReady();
    await user.click(screen.getByLabelText("Aumentar zoom"));
    expect(controller.zoomIn).toHaveBeenCalledOnce();
    expect(screen.getByLabelText("Zoom actual")).toHaveTextContent("110%");
    await user.click(screen.getByLabelText("Reducir zoom"));
    expect(controller.zoomOut).toHaveBeenCalledOnce();
  });

  it("[47] activates fit width", async () => {
    const { controller, user } = await renderReady();
    await user.click(screen.getByRole("button", { name: "Ajustar ancho" }));
    expect(controller.setScaleMode).toHaveBeenCalledWith("page-width");
  });

  it("[48] activates fit page", async () => {
    const { controller, user } = await renderReady();
    await user.click(screen.getByRole("button", { name: "Ajustar página" }));
    expect(controller.setScaleMode).toHaveBeenCalledWith("page-fit");
  });

  it("[49] activates actual size", async () => {
    const { controller, user } = await renderReady();
    await user.click(screen.getByRole("button", { name: "Tamaño real" }));
    expect(controller.setScaleMode).toHaveBeenCalledWith("page-actual");
  });

  it("[50] rotates clockwise", async () => {
    const { controller, user } = await renderReady();
    await user.click(screen.getByLabelText("Rotar a la derecha"));
    expect(controller.rotateClockwise).toHaveBeenCalledOnce();
    expect(screen.getByLabelText("Rotación actual")).toHaveTextContent("90°");
  });

  it("[51] rotates counterclockwise", async () => {
    const { controller, user } = await renderReady();
    await user.click(screen.getByLabelText("Rotar a la izquierda"));
    expect(controller.rotateCounterclockwise).toHaveBeenCalledOnce();
    expect(screen.getByLabelText("Rotación actual")).toHaveTextContent("270°");
  });

  it("[52] renders a compact metadata card without paths", async () => {
    await renderReady();
    expect(screen.getByRole("heading", { name: metadata.title })).toBeVisible();
    expect(screen.getByText(metadata.source.name)).toBeVisible();
    expect(screen.getByText(metadata.version.original_filename)).toBeVisible();
    expect(document.body).not.toHaveTextContent("/home/");
  });

  it("[53] keeps PDF page and Book page labels distinct", async () => {
    const { controller } = await renderReady();
    act(() => controller.goToPage(9));
    expect(screen.getByLabelText("PDF page")).toHaveValue("9");
    await waitFor(() => expect(screen.getByText("Book page 7 · PDF page 9")).toBeVisible());
  });

  it("[54] saves reading position only after an explicit click", async () => {
    const api = makeApi();
    const { user } = await renderReady(api);
    expect(api.savePage).not.toHaveBeenCalled();
    await user.click(screen.getByRole("button", { name: "Guardar posición" }));
    expect(api.savePage).toHaveBeenCalledWith(DOCUMENT_ID, 3);
    expect(await screen.findByText("Posición guardada.")).toBeVisible();
  });

  it("[55] delegates next and previous PDF.js search", async () => {
    const { controller, user } = await renderReady();
    await user.type(screen.getByLabelText("Buscar en el PDF"), "variedad");
    fireEvent.keyDown(screen.getByLabelText("Buscar en el PDF"), { key: "Enter" });
    expect(controller.search).toHaveBeenCalledWith(
      "variedad",
      "next",
      { caseSensitive: false, entireWord: false },
      false,
    );
    await user.click(screen.getByLabelText("Coincidencia anterior"));
    expect(controller.search).toHaveBeenLastCalledWith(
      "variedad",
      "previous",
      { caseSensitive: false, entireWord: false },
      true,
    );
  });

  it("[56] reports a PDF.js no-results state", async () => {
    const { controller } = await renderReady();
    act(() => controller.emitSearch({ status: "not_found", current: 0, total: 0 }));
    expect(screen.getByText("Sin resultados")).toBeVisible();
  });

  it("[57] displays a valid same-page text selection", async () => {
    const { controller } = await renderReady();
    act(() => controller.emitSelection(samePageSelection));
    expect(screen.getByRole("heading", { name: "Selección válida de una página" })).toBeVisible();
    expect(screen.getByText(samePageSelection.selected_text)).toBeVisible();
    expect(screen.getByText("Rectángulos").parentElement).toHaveTextContent("1");
  });
});

describe("S5A frontend requirements 60-66", () => {
  it("[60] warns and omits geometry for a cross-page selection", async () => {
    const { controller } = await renderReady();
    act(() => controller.emitSelection(crossPageSelection));
    expect(screen.getByRole("heading", { name: "Selección multipágina" })).toBeVisible();
    expect(screen.getByText(/no se genera geometría utilizable/)).toBeVisible();
    expect(screen.getByText("Rectángulos").parentElement).toHaveTextContent("0");
  });

  it("[61] clears the ephemeral selection", async () => {
    const { controller, user } = await renderReady();
    act(() => controller.emitSelection(samePageSelection));
    await user.click(screen.getByRole("button", { name: "Limpiar selección" }));
    expect(controller.clearSelection).toHaveBeenCalledWith("user");
    expect(screen.getByRole("heading", { name: "Sin selección" })).toBeVisible();
  });

  it("[62] selection never calls the persistence API", async () => {
    const api = makeApi();
    const { controller } = await renderReady(api);
    act(() => controller.emitSelection(samePageSelection));
    await screen.findByText(samePageSelection.selected_text);
    expect(api.savePage).not.toHaveBeenCalled();
  });

  it("[63] exposes no highlight or underline persistence button", async () => {
    const { controller } = await renderReady();
    act(() => controller.emitSelection(samePageSelection));
    expect(screen.queryByRole("button", { name: /highlight|subrayar/i })).not.toBeInTheDocument();
    expect(screen.getAllByText(/Inicializa Notes & Evidence/).length).toBeGreaterThan(0);
  });

  it("[64] exposes no concept-link write action", async () => {
    const { controller } = await renderReady();
    act(() => controller.emitSelection(samePageSelection));
    expect(screen.queryByRole("button", { name: /concepto|concept/i })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /crear annotation/i })).not.toBeInTheDocument();
  });

  it("[65] exposes no arbitrary URL input", async () => {
    await renderReady();
    expect(document.querySelector('input[type="url"]')).not.toBeInTheDocument();
    expect(screen.queryByLabelText(/URL del PDF|URL arbitraria/i)).not.toBeInTheDocument();
  });

  it("[66] exposes no filesystem or Mongo path input", async () => {
    await renderReady();
    expect(screen.queryByLabelText(/path|ruta local|Mongo URI/i)).not.toBeInTheDocument();
    expect(document.querySelector('input[type="file"]')).not.toBeInTheDocument();
  });
});
