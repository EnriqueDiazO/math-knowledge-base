import { beforeEach, afterEach, it, expect, vi } from "vitest";
import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
  act,
} from "@testing-library/react";
import { SavedNoteActions } from "../src/study/SavedNoteActions";
import type { StudyContext } from "../src/study/api";
const context = { library_id: "owned", runtime_id: "runtime" } as StudyContext;
const note = { title: "Nota histórica", revision: "a".repeat(64) };
const key = (family: string) =>
  "mathmongo-note-actions-v1-owned-" + family + "-original";
const click = (name: string) =>
  fireEvent.click(screen.getByRole("button", { name }));
const fill = (name: string, value: string) =>
  fireEvent.change(screen.getByLabelText(name, { exact: true }), {
    target: { value },
  });
beforeEach(() => localStorage.clear());
afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});
for (const family of ["cornell", "cpi"] as const) {
  it(
    family +
      ": recovers the exact copy attempt without the original page or another insert",
    async () => {
      const navigate = vi.fn(),
        refresh = vi.fn(),
        bodies: Record<string, string>[] = [];
      let fail = true;
      vi.stubGlobal(
        "fetch",
        vi.fn(async (_url, options) => {
          const body = JSON.parse(options.body);
          bodies.push(body);
          if (fail) throw Error("Lost response");
          return Response.json({
            note_id: family + "_copy_" + body.request_id,
            revision: "b".repeat(64),
          });
        }),
      );
      const view = render(
        <SavedNoteActions
          context={context}
          family={family}
          identity="original"
          note={note}
          navigate={navigate}
          refresh={refresh}
        />,
      );
      fireEvent.click(screen.getByText("Gestionar esta nota"));
      click("Duplicar nota completa");
      fill("Título de la copia", "Copia propia");
      click("Crear copia de esta nota");
      await screen.findByRole("button", {
        name: "Reintentar la misma operación",
      });
      await waitFor(() =>
        expect(screen.getByRole("status")).not.toHaveTextContent(
          "Esperando confirmación",
        ),
      );
      const raw = localStorage.getItem(key(family));
      view.unmount();
      fail = false;
      render(
        <SavedNoteActions
          context={context}
          family={family}
          identity="original"
          navigate={navigate}
          refresh={refresh}
        />,
      );
      click("Reintentar la misma operación");
      await waitFor(() => expect(navigate).toHaveBeenCalled());
      expect(bodies).toHaveLength(2);
      expect(bodies[1]).toEqual(bodies[0]);
      expect(bodies[0]).toMatchObject({
        action: "duplicate",
        title: "Copia propia",
        revision: note.revision,
      });
      expect(JSON.parse(raw!).pending).toBe(JSON.stringify(bodies[0]));
      expect(localStorage.getItem(key(family))).toBeNull();
    },
  );
}
it("requires the reviewed note name, keeps the document draft and rejects an unconfirmed deletion response", async () => {
  const navigate = vi.fn(),
    requests: Record<string, string>[] = [];
  let confirmed = false;
  localStorage.setItem("mathmongo-diary-v1-owned-original", "raw draft intact");
  vi.stubGlobal(
    "fetch",
    vi.fn(async (_url, options) => {
      requests.push(JSON.parse(options.body));
      return Response.json({
        status: confirmed ? "deleted" : "saved",
        family: "diary",
        note_id: "original",
      });
    }),
  );
  render(
    <SavedNoteActions
      context={context}
      family="diary"
      identity="original"
      note={note}
      navigate={navigate}
      refresh={vi.fn()}
    />,
  );
  fireEvent.click(screen.getByText("Gestionar esta nota"));
  click("Eliminar nota guardada…");
  fill("Escribe el nombre de la nota para confirmar", "Otra nota");
  expect(
    screen.getByRole("button", { name: "Confirmar eliminación de esta nota" }),
  ).toBeDisabled();
  expect(requests).toHaveLength(0);
  fill("Escribe el nombre de la nota para confirmar", note.title);
  click("Confirmar eliminación de esta nota");
  await screen.findByText(/No se confirmó la eliminación/);
  expect(navigate).not.toHaveBeenCalled();
  confirmed = true;
  click("Reintentar la misma operación");
  await waitFor(() => expect(navigate).toHaveBeenCalledWith("/study/notebook"));
  expect(requests[1]).toEqual(requests[0]);
  expect(localStorage.getItem("mathmongo-diary-v1-owned-original")).toBe(
    "raw draft intact",
  );
});
it("does not apply a late result to another library or erase the old pending operation", async () => {
  const navigate = vi.fn();
  let resolve!: (value: Response) => void;
  vi.stubGlobal(
    "fetch",
    vi.fn(
      () =>
        new Promise<Response>((done) => {
          resolve = done;
        }),
    ),
  );
  const view = render(
    <SavedNoteActions
      context={context}
      family="diary"
      identity="original"
      note={note}
      navigate={navigate}
      refresh={vi.fn()}
    />,
  );
  fireEvent.click(screen.getByText("Gestionar esta nota"));
  click("Eliminar nota guardada…");
  fill("Escribe el nombre de la nota para confirmar", note.title);
  click("Confirmar eliminación de esta nota");
  const raw = localStorage.getItem(key("diary"));
  view.unmount();
  render(
    <SavedNoteActions
      context={{ ...context, library_id: "other" }}
      family="diary"
      identity="original"
      note={note}
      navigate={navigate}
      refresh={vi.fn()}
    />,
  );
  await act(async () =>
    resolve(
      Response.json({
        status: "deleted",
        note_id: "original",
        family: "diary",
      }),
    ),
  );
  expect(navigate).not.toHaveBeenCalled();
  expect(localStorage.getItem(key("diary"))).toBe(raw);
  expect(screen.queryByText("Reintentar la misma operación")).toBeNull();
});
it("requires a new deliberate confirmation after a conflict, rather than silently adopting a revision", async () => {
  const navigate = vi.fn(),
    refresh = vi.fn();
  vi.stubGlobal(
    "fetch",
    vi.fn(async () =>
      Response.json(
        {
          error: {
            code: "catalog_conflict",
            message: "Otra ventana cambió la nota",
          },
        },
        { status: 409 },
      ),
    ),
  );
  const view = render(
    <SavedNoteActions
      context={context}
      family="diary"
      identity="original"
      note={note}
      navigate={navigate}
      refresh={refresh}
    />,
  );
  fireEvent.click(screen.getByText("Gestionar esta nota"));
  click("Eliminar nota guardada…");
  fill("Escribe el nombre de la nota para confirmar", note.title);
  click("Confirmar eliminación de esta nota");
  await waitFor(() =>
    expect(JSON.parse(localStorage.getItem(key("diary"))!).pending).toBe(""),
  );
  click("Consultar versión actual de la nota");
  expect(refresh).toHaveBeenCalledOnce();
  view.rerender(
    <SavedNoteActions
      context={context}
      family="diary"
      identity="original"
      note={{ ...note, revision: "b".repeat(64) }}
      navigate={navigate}
      refresh={refresh}
    />,
  );
  expect(
    screen.getByRole("button", { name: "Confirmar eliminación de esta nota" }),
  ).toBeDisabled();
  expect(navigate).not.toHaveBeenCalled();
  expect(fetch).toHaveBeenCalledOnce();
});
it("does not send an operation if its request cannot be preserved locally", () => {
  vi.stubGlobal("fetch", vi.fn());
  render(
    <SavedNoteActions
      context={context}
      family="diary"
      identity="original"
      note={note}
      navigate={vi.fn()}
      refresh={vi.fn()}
    />,
  );
  fireEvent.click(screen.getByText("Gestionar esta nota"));
  vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => {
    throw Error("Quota");
  });
  click("Eliminar nota guardada…");
  expect(screen.getByRole("alert")).toHaveTextContent("no pudo conservar");
  expect(fetch).not.toHaveBeenCalled();
});
it("keeps a corrupt pending payload intact and explains recovery instead of sending it", async () => {
  const raw = JSON.stringify({
    mode: "delete",
    reviewTitle: note.title,
    revision: note.revision,
    typed: note.title,
    title: "",
    pending: "{broken",
  });
  localStorage.setItem(key("diary"), raw);
  vi.stubGlobal("fetch", vi.fn());
  render(
    <SavedNoteActions
      context={context}
      family="diary"
      identity="original"
      navigate={vi.fn()}
      refresh={vi.fn()}
    />,
  );
  click("Reintentar la misma operación");
  await screen.findByText(/No pudimos leer la solicitud local/);
  expect(fetch).not.toHaveBeenCalled();
  expect(localStorage.getItem(key("diary"))).toBe(raw);
});
