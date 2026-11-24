import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { CatalogEditor } from "../src/study/CatalogEditor";
import type { StudyContext } from "../src/study/api";
const context = { library_id: "owned", runtime_id: "runtime" } as StudyContext;
const revision = "a".repeat(64),
  nextRevision = "b".repeat(64);
let source: Record<string, unknown>,
  writes: Record<string, unknown>[],
  lost: boolean,
  conflict: boolean;
beforeEach(() => {
  localStorage.clear();
  writes = [];
  lost = false;
  conflict = false;
  source = {
    source_id: "src-owned",
    revision,
    status: "active",
    name: "Original",
    source_type: "book",
    description: "Inicial",
    tags: ["old"],
    aliases: [],
    rights_default: { copyright_status: "unknown", redistribution: "ask" },
  };
  vi.stubGlobal(
    "fetch",
    vi.fn(async (input, options) => {
      if (String(input).includes("/catalog/preparation"))
        return Response.json({ state: "ready", version: "1" });
      if (options?.method === "POST") {
        const body = JSON.parse(String(options.body));
        writes.push(body);
        if (conflict)
          return Response.json(
            {
              error: {
                code: "catalog_conflict",
                message:
                  "Otra ventana cambió la ficha. El borrador se conserva.",
              },
            },
            { status: 409 },
          );
        source = { ...source, ...body.changes, revision: nextRevision };
        if (lost) {
          lost = false;
          throw new TypeError("lost");
        }
      }
      return Response.json(source);
    }),
  );
});
afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});
it("retries the exact persisted source edit after a lost response and reload", async () => {
  const user = userEvent.setup(),
    done = vi.fn();
  let view = render(
    <CatalogEditor
      context={context}
      sourceId="src-owned"
      kind="source"
      identity="src-owned"
      done={done}
    />,
  );
  const name = await screen.findByLabelText("Nombre de la fuente");
  await user.clear(name);
  await user.type(name, "Nombre nuevo");
  lost = true;
  await user.click(screen.getByRole("button", { name: "Guardar cambios" }));
  await screen.findByText(/No se confirmó la conexión/u);
  view.unmount();
  view = render(
    <CatalogEditor
      context={context}
      sourceId="src-owned"
      kind="source"
      identity="src-owned"
      done={done}
    />,
  );
  await user.click(
    await screen.findByRole("button", { name: "Reintentar el mismo guardado" }),
  );
  await waitFor(() => expect(done).toHaveBeenCalledTimes(1));
  expect(writes).toHaveLength(2);
  expect(writes[1]).toEqual(writes[0]);
  expect(writes[0]).toMatchObject({
    revision,
    changes: { name: "Nombre nuevo" },
  });
  view.unmount();
});
it("keeps a conflicting draft and rebases only the fields the user changed", async () => {
  const user = userEvent.setup(),
    done = vi.fn();
  render(
    <CatalogEditor
      context={context}
      sourceId="src-owned"
      kind="source"
      identity="src-owned"
      done={done}
    />,
  );
  const name = await screen.findByLabelText("Nombre de la fuente");
  await user.clear(name);
  await user.type(name, "Mi cambio");
  source = {
    ...source,
    description: "Cambio concurrente",
    tags: ["Nuevo"],
    revision: nextRevision,
  };
  conflict = true;
  await user.click(screen.getByRole("button", { name: "Guardar cambios" }));
  await screen.findByText(/Otra ventana cambió/u);
  expect(screen.getByLabelText("Nombre de la fuente")).toHaveValue("Mi cambio");
  expect(done).not.toHaveBeenCalled();
  await user.click(
    screen.getByRole("button", { name: "Revisar versión actual" }),
  );
  await user.click(
    await screen.findByRole("button", {
      name: "Continuar editando sobre esta versión",
    }),
  );
  expect(screen.getByLabelText("Descripción")).toHaveValue(
    "Cambio concurrente",
  );
  conflict = false;
  await user.click(screen.getByRole("button", { name: "Guardar cambios" }));
  await waitFor(() => expect(done).toHaveBeenCalledTimes(1));
  expect(writes[1]).toMatchObject({
    revision: nextRevision,
    changes: { name: "Mi cambio" },
  });
});
it("records explicit shared-reference consent in a retry that survives reload", async () => {
  const user = userEvent.setup(),
    done = vi.fn();
  source = {
    reference_id: "ref-owned",
    revision,
    status: "active",
    source_ids: ["first", "second"],
    reference_type: "article",
    title: "Original",
    authors: [{ family: "Noether", given: "Emmy", orcid: "kept" }],
    year: 1918,
    bibtex: { key: "Original", extra: { custom: "kept" } },
  };
  let view = render(
    <CatalogEditor
      context={context}
      sourceId="first"
      kind="reference"
      identity="ref-owned"
      done={done}
    />,
  );
  const title = await screen.findByLabelText("Título de la referencia");
  await user.clear(title);
  await user.type(title, "Título corregido");
  await user.click(screen.getByRole("button", { name: "Guardar cambios" }));
  expect(writes).toHaveLength(0);
  await user.click(
    screen.getByRole("checkbox", { name: /Aplicar estos cambios/u }),
  );
  lost = true;
  await user.click(screen.getByRole("button", { name: "Guardar cambios" }));
  await screen.findByText(/No se confirmó la conexión/u);
  view.unmount();
  view = render(
    <CatalogEditor
      context={context}
      sourceId="first"
      kind="reference"
      identity="ref-owned"
      done={done}
    />,
  );
  await user.click(
    await screen.findByRole("button", { name: "Reintentar el mismo guardado" }),
  );
  await waitFor(() => expect(done).toHaveBeenCalledTimes(1));
  expect(writes[0]).toMatchObject({
    acknowledge_shared: true,
    changes: { title: "Título corregido" },
  });
  expect(writes[0]).not.toHaveProperty("authors");
  expect(writes[1]).toEqual(writes[0]);
  view.unmount();
});
