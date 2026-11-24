import { afterEach, expect, it, vi } from "vitest";
import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import { NotebookPages } from "../src/study/NotebookPages";
import type { StudyContext } from "../src/study/api";

vi.mock("../src/study/NotebookWorkspace", () => ({
  NotebookWorkspace: () => <p>Editor compartido</p>,
}));
const context = { library_id: "owned", runtime_id: "runtime" } as StudyContext;
afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});
it("searches and paginates a source's Diario summaries without opening any full body", async () => {
  const navigate = vi.fn(),
    fetch = vi.fn(async (_input: unknown) =>
      Response.json({
        items: [
          {
            note_id: "saved",
            title: "Entrada confirmada",
            date: "2026-11-24",
            project: "Álgebra",
            context: "estudio",
          },
        ],
        page: 1,
        total: 21,
      }),
    );
  vi.stubGlobal("fetch", fetch);
  render(
    <NotebookPages
      context={context}
      navigate={navigate}
      identity=""
      search="?source=src-owned"
    />,
  );
  expect(
    await screen.findByRole("link", { name: "Entrada confirmada" }),
  ).toHaveAttribute("href", "/study/notebook/saved");
  await waitFor(() => expect(fetch).toHaveBeenCalledTimes(1));
  expect(String(fetch.mock.calls[0]?.[0])).toContain("source_id=src-owned");
  fireEvent.change(screen.getByLabelText("Buscar en el Cuaderno"), {
    target: { value: "Texto [literal]" },
  });
  fireEvent.change(screen.getByLabelText("Filtrar por proyecto"), {
    target: { value: "Álgebra" },
  });
  expect(
    screen.getByRole("button", { name: "Buscar entradas" }),
  ).toHaveAttribute("type", "submit");
  fireEvent.click(screen.getByRole("button", { name: "Buscar entradas" }));
  const searched = new URL(navigate.mock.calls[0][0], "http://localhost");
  expect(searched.searchParams.get("q")).toBe("Texto [literal]");
  expect(searched.searchParams.get("project")).toBe("Álgebra");
  expect(searched.searchParams.get("source")).toBe("src-owned");
  fireEvent.click(screen.getByRole("button", { name: "Más entradas" }));
  expect(
    new URL(navigate.mock.calls[1][0], "http://localhost").searchParams.get(
      "page",
    ),
  ).toBe("2");
  expect(fetch).toHaveBeenCalledTimes(1); // Navigation has not requested any full document.
});
it("keeps a structured-format failure visible and retries without mounting a misleading empty editor", async () => {
  let retry = false;
  const fetch = vi.fn(async () =>
    retry
      ? Response.json({ note_id: "historical", title: "Recuperada" })
      : Response.json(
          {
            error: {
              code: "catalog_conflict",
              message: "Esta entrada requiere el editor Cornell.",
            },
          },
          { status: 409 },
        ),
  );
  vi.stubGlobal("fetch", fetch);
  render(
    <NotebookPages
      context={context}
      navigate={vi.fn()}
      identity="historical"
      search=""
    />,
  );
  expect(await screen.findByRole("alert")).toHaveTextContent("editor Cornell");
  expect(screen.queryByText("Editor compartido")).toBeNull();
  retry = true;
  fireEvent.click(screen.getByRole("button", { name: "Reintentar entrada" }));
  expect(await screen.findByText("Editor compartido")).toBeVisible();
});
