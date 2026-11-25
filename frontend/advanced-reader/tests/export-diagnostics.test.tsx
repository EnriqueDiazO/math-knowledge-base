import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, expect, test, vi } from "vitest";
import { ExportActions } from "../src/study/ExportActions";
import type { StudyContext } from "../src/study/api";
afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});
test("failed PDF offers the log promised by the message without claiming a download succeeded", async () => {
  const diagnostic =
    "/inputs/main.tex:80: Missing example\nl.80 \\listoffigures";
  vi.stubGlobal(
    "fetch",
    vi
      .fn()
      .mockResolvedValue({
        ok: false,
        json: async () => ({
          error: {
            code: "notebook_export_failed",
            message: "Consulta Detalles de compilación.",
            diagnostic,
          },
        }),
      }),
  );
  render(
    <ExportActions
      context={{ library_id: "owned", runtime_id: "runtime" } as StudyContext}
      notebookId="saved"
    />,
  );
  fireEvent.click(screen.getByRole("button", { name: "Exportar PDF" }));
  await screen.findByText("Consulta Detalles de compilación.");
  fireEvent.click(screen.getByText("Detalles de compilación", { exact: true }));
  expect(document.querySelector("pre")?.textContent).toBe(diagnostic);
  expect(
    screen.getByRole("button", { name: "Descargar registro de compilación" }),
  ).toBeTruthy();
  expect(screen.queryByText(/Descarga preparada/)).toBeNull();
});
