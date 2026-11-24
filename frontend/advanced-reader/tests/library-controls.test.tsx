import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { BibtexImport } from "../src/study/BibtexImport";
import { ReferencePicker } from "../src/study/ReferencePicker";
import { CatalogStateAction } from "../src/study/CatalogStateAction";
import type { StudyContext } from "../src/study/api";
const context = { library_id: "owned", runtime_id: "runtime" } as StudyContext;
beforeEach(() => localStorage.clear());
afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});
it("imports only selected BibTeX entries and retains the reviewed input on conflict", async () => {
  const user = userEvent.setup(),
    done = vi.fn(),
    writes: unknown[] = [];
  vi.stubGlobal(
    "fetch",
    vi.fn(async (input, options) => {
      const path = String(input);
      if (path.endsWith("/catalog/preparation"))
        return Response.json({ state: "ready" });
      if (path.endsWith("/preview"))
        return Response.json({
          candidates: [
            {
              entry_index: 0,
              citekey: "one",
              reference_data: { title: "One" },
              warnings: [],
            },
            {
              entry_index: 1,
              citekey: "two",
              reference_data: { title: "Two" },
              warnings: [],
            },
          ],
          errors: [],
        });
      writes.push(JSON.parse(String(options?.body)));
      return Response.json({
        saved: 0,
        items: [{ entry_index: 1, status: "duplicates" }],
      });
    }),
  );
  render(<BibtexImport context={context} sourceId="source" done={done} />);
  await user.type(
    screen.getByLabelText("Contenido BibTeX"),
    "Contenido conservado",
  );
  await user.click(
    screen.getByRole("button", { name: "Revisar entradas BibTeX" }),
  );
  await user.click(await screen.findByRole("checkbox", { name: "Two" }));
  await user.click(
    screen.getByRole("button", { name: "Importar referencias seleccionadas" }),
  );
  await screen.findByText(/Hay coincidencias/u);
  expect(writes[0]).toMatchObject({
    selected: [1],
    content: "Contenido conservado",
  });
  expect(done).not.toHaveBeenCalled();
  expect(screen.getByLabelText("Contenido BibTeX")).toHaveValue(
    "Contenido conservado",
  );
});
it("keeps a corrupt BibTeX selection for recovery instead of importing extra entries", () => {
  const raw = JSON.stringify({
    operation_id: "original",
    content: "No perder",
    selection: "{bad",
  });
  localStorage.setItem("mathmongo-bibtex-v1-ownedsource", raw);
  render(<BibtexImport context={context} sourceId="source" done={vi.fn()} />);
  expect(screen.getByRole("alert").textContent).toContain(
    "original se conserva",
  );
  expect(
    screen.queryByRole("button", {
      name: "Importar referencias seleccionadas",
    }),
  ).toBeNull();
  expect(localStorage.getItem("mathmongo-bibtex-v1-ownedsource")).toBe(raw);
});
it("searches beyond the first page while retaining a reference absent from that page", async () => {
  const user = userEvent.setup(),
    changed = vi.fn();
  vi.stubGlobal(
    "fetch",
    vi.fn(async (input) =>
      Response.json(
        String(input).includes("page=2")
          ? {
              items: [
                {
                  reference_id: "last",
                  title: "Última referencia",
                  status: "active",
                },
              ],
              total: 21,
              page: 2,
            }
          : {
              items: [
                { reference_id: "first", title: "Primera", status: "active" },
              ],
              total: 21,
              page: 1,
            },
      ),
    ),
  );
  render(
    <ReferencePicker
      context={context}
      sourceId="source"
      value="last"
      changed={changed}
    />,
  );
  expect(screen.getByRole("combobox")).toHaveValue("last");
  await user.click(
    await screen.findByRole("button", { name: "Más referencias" }),
  );
  await screen.findByRole("option", { name: "Última referencia" });
  await user.selectOptions(screen.getByRole("combobox"), "last");
  expect(changed).toHaveBeenCalledWith("last");
});
it("announces archive only after a backend-confirmed status and keeps a failed action retryable", async () => {
  const user = userEvent.setup(),
    done = vi.fn();
  const fetch = vi
    .fn()
    .mockResolvedValueOnce(Response.json({ status: "active" }))
    .mockResolvedValueOnce(Response.json({ status: "archived" }));
  vi.stubGlobal("fetch", fetch);
  render(
    <CatalogStateAction
      context={context}
      path="/sources/source"
      status="active"
      revision={"a".repeat(64)}
      kind="fuente"
      done={done}
    />,
  );
  expect(
    screen.getByRole("button", { name: "Archivar fuente", hidden: true }),
  ).toBeDisabled();
  await user.click(screen.getByText("Organizar fuente"));
  await user.click(
    screen.getByRole("checkbox", { name: "Confirmar archivar fuente" }),
  );
  await user.click(screen.getByRole("button", { name: "Archivar fuente" }));
  await screen.findByText(/No se confirmó el estado/u);
  expect(done).not.toHaveBeenCalled();
  await user.click(screen.getByRole("button", { name: "Archivar fuente" }));
  await waitFor(() => expect(done).toHaveBeenCalledTimes(1));
});
