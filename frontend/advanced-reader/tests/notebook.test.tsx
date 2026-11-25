import { afterEach, beforeEach, expect, it, vi } from "vitest";
import {
  act,
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import { useEffect, useRef } from "react";
import type {
  DocumentEditor,
  EditorSnapshot,
} from "../src/knowledge-map/document-editor";
import { NotebookWorkspace } from "../src/study/NotebookWorkspace";
import {
  diaryChanges,
  diaryDraft,
  diaryFields,
  diaryRebase,
  diarySnapshot,
  type DiaryDetail,
} from "../src/study/notebook-state";
import type { StudyContext } from "../src/study/api";

// Transport/draft boundary only. The owned browser scenarios use real Tiptap/MathLive.
vi.mock("../src/study/DocumentSurface", () => ({
  DocumentContent: ({ content }: { content: string }) => <p>{content}</p>,
  DocumentSurface: ({
    initial,
    changed,
    editorRef,
  }: {
    initial: string;
    changed: (body: string, snapshot: EditorSnapshot) => void;
    editorRef: { current: DocumentEditor | null };
  }) => {
    const content = useRef(initial),
      onChange = useRef(changed);
    onChange.current = changed;
    useEffect(() => {
      const snapshot = {
        json: { type: "doc" },
        selection: 1,
        scroll: 0,
        sourceMode: true,
      };
      editorRef.current = {
        value: () => content.current,
        snapshot: () => snapshot,
        valid: () => !content.current.includes("unfinished"),
      } as unknown as DocumentEditor;
      return () => {
        onChange.current(content.current, snapshot);
        editorRef.current = null;
      };
    }, [editorRef]);
    return (
      <textarea
        aria-label="Contenido de prueba"
        defaultValue={initial}
        onChange={(event) => {
          content.current = event.target.value;
          onChange.current(content.current, {
            json: { type: "doc" },
            selection: 1,
            scroll: 0,
            sourceMode: true,
          });
        }}
      />
    );
  },
}));
vi.mock("../src/study/NotebookReferences", () => ({
  NotebookReferences: () => <p>Referencias conservadas</p>,
}));
const context = { library_id: "owned", runtime_id: "runtime" } as StudyContext;
const original: DiaryDetail = {
  note_id: "historical",
  revision: "a".repeat(64),
  title: "Histórica",
  date: "2026-11-24",
  context: "estudio",
  project: "Álgebra",
  tags: ["coma, literal"],
  latex_body: "\\macroDesconocida{α}\n",
  references: [],
  image_count: 1,
};
const key = (identity = "new", library = "owned") =>
  "mathmongo-diary-v1-" + library + "-" + identity;
beforeEach(() => localStorage.clear());
afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});
it("retains exact source, literal comma tags and historical missing dates in an unchanged edit", () => {
  const draft = diaryDraft({ ...original, date: "" });
  expect(diaryChanges(draft)).toEqual({});
  expect(diaryFields(draft).latex_body).toBe(original.latex_body);
  expect(diaryFields(draft).tags).toEqual(["coma, literal"]);
  expect(draft.date).toBe("");
});
it("rebases only the user's changed fields and keeps the remote source when only the title was edited", () => {
  const draft = {
    ...diaryDraft(original),
    title: "Mi título",
    snapshot: '{"selection":1}',
  };
  const next = diaryRebase(draft, {
    ...original,
    revision: "b".repeat(64),
    latex_body: "Cuerpo remoto",
    project: "Proyecto remoto",
  });
  expect(next.title).toBe("Mi título");
  expect(next.latex_body).toBe("Cuerpo remoto");
  expect(next.project).toBe("Proyecto remoto");
  expect(next.snapshot).toBe("");
  expect(diaryChanges(next)).toEqual({ title: "Mi título" });
});
it("rejects damaged reference and editor recovery data without substituting empty content", () => {
  expect(() =>
    diaryFields({ ...diaryDraft(original), references: "[1]" }),
  ).toThrow(/dañadas/);
  expect(() =>
    diaryChanges({ ...diaryDraft(original), original: "{}" }),
  ).toThrow(/no es válida/);
  expect(() => diarySnapshot({ snapshot: "[]" })).toThrow(/no es válida/);
  expect(diarySnapshot({ snapshot: "" })).toBeUndefined();
});
it("recovers and retries exactly one creation after a lost reply, then prevents a cleanup from recreating its draft", async () => {
  const navigate = vi.fn(),
    writes: unknown[] = [];
  let stored: DiaryDetail | undefined;
  vi.stubGlobal(
    "fetch",
    vi.fn(async (_input, options) => {
      const body = JSON.parse(String(options?.body));
      writes.push(body);
      if (!stored) {
        stored = {
          ...original,
          ...body,
          note_id: "diary-created",
          references: [],
        };
        throw new TypeError("lost");
      }
      return Response.json(stored);
    }),
  );
  let view = render(
    <NotebookWorkspace context={context} navigate={navigate} />,
  );
  fireEvent.change(screen.getByLabelText("Título de la entrada"), {
    target: { value: "Nueva" },
  });
  fireEvent.change(screen.getByLabelText("Contenido de prueba"), {
    target: { value: "Texto $x$ sin pérdida" },
  });
  fireEvent.click(screen.getByRole("button", { name: "Guardar entrada" }));
  await screen.findByText(/No se confirmó la conexión/);
  view.unmount();
  view = render(<NotebookWorkspace context={context} navigate={navigate} />);
  expect(screen.getByLabelText("Contenido de prueba")).toHaveValue(
    "Texto $x$ sin pérdida",
  );
  fireEvent.click(
    screen.getByRole("button", { name: "Reintentar el mismo guardado" }),
  );
  await waitFor(() =>
    expect(navigate).toHaveBeenCalledWith("/study/notebook/diary-created"),
  );
  view.unmount();
  expect(writes).toHaveLength(2);
  expect(writes[1]).toEqual(writes[0]);
  expect(localStorage.getItem(key())).toBeNull();
});
it("retains the pending edit when the server response does not confirm its actual content", async () => {
  vi.stubGlobal(
    "fetch",
    vi.fn(async () => Response.json({ ...original, latex_body: "Distinto" })),
  );
  render(
    <NotebookWorkspace context={context} note={original} navigate={vi.fn()} />,
  );
  fireEvent.change(screen.getByLabelText("Contenido de prueba"), {
    target: { value: "Cambio propio" },
  });
  fireEvent.click(screen.getByRole("button", { name: "Guardar entrada" }));
  await screen.findByText(/No se confirmó el contenido/);
  expect(
    screen.getByRole("button", { name: "Reintentar el mismo guardado" }),
  ).toBeEnabled();
  expect(JSON.parse(localStorage.getItem(key("historical"))!).latex_body).toBe(
    "Cambio propio",
  );
});
it("reviews a real conflict explicitly and never restores the destroyed editor's old source over the new baseline", async () => {
  const remote = {
    ...original,
    revision: "b".repeat(64),
    latex_body: "Cuerpo de otra ventana",
    project: "Remoto",
  };
  let saved: unknown;
  vi.stubGlobal(
    "fetch",
    vi.fn(async (_input, options) => {
      if (!options?.body) return Response.json(remote);
      const body = JSON.parse(String(options.body));
      if (body.revision === original.revision)
        return Response.json(
          {
            error: {
              code: "catalog_conflict",
              message: "Otra ventana cambió la entrada.",
            },
          },
          { status: 409 },
        );
      saved = body;
      return Response.json({ ...remote, ...body.changes });
    }),
  );
  render(
    <NotebookWorkspace context={context} note={original} navigate={vi.fn()} />,
  );
  fireEvent.change(screen.getByLabelText("Título de la entrada"), {
    target: { value: "Título propio" },
  });
  fireEvent.click(screen.getByRole("button", { name: "Guardar entrada" }));
  await screen.findByText(/Otra ventana cambió la entrada/);
  expect(screen.getByLabelText("Contenido de prueba")).toHaveValue(
    original.latex_body,
  );
  fireEvent.click(
    screen.getByRole("button", { name: "Consultar versión guardada" }),
  );
  fireEvent.click(
    await screen.findByRole("button", { name: "Continuar sobre esta versión" }),
  );
  expect(screen.getByLabelText("Contenido de prueba")).toHaveValue(
    remote.latex_body,
  );
  expect(screen.getByLabelText("Título de la entrada")).toHaveValue(
    "Título propio",
  );
  fireEvent.click(screen.getByRole("button", { name: "Guardar entrada" }));
  await screen.findByText("Entrada guardada y confirmada en esta biblioteca.");
  expect(saved).toEqual({
    revision: remote.revision,
    changes: { title: "Título propio" },
  });
});
it("keeps corrupt recovery records intact and restarts only with an archived copy", async () => {
  const raw = JSON.stringify({ ...diaryDraft(original), snapshot: "[bad" });
  localStorage.setItem(key("historical"), raw);
  render(
    <NotebookWorkspace context={context} note={original} navigate={vi.fn()} />,
  );
  expect(screen.getByRole("alert")).toHaveTextContent(/JSON/);
  expect(screen.queryByLabelText("Contenido de prueba")).toBeNull();
  expect(localStorage.getItem(key("historical"))).toBe(raw);
  fireEvent.click(screen.getByRole("button", { name: "Reiniciar con copia" }));
  expect(await screen.findByLabelText("Contenido de prueba")).toHaveValue(
    original.latex_body,
  );
  expect(
    Object.keys(localStorage).some(
      (k) => k.includes("archive-") && localStorage.getItem(k) === raw,
    ),
  ).toBe(true);
});
it("keeps the editor and its latest copy usable when all draft storage fails", async () => {
  const id = key("historical"),
    legacy = JSON.stringify({ ...diaryDraft(original), title: "Copia anterior" });
  localStorage.setItem(id, legacy);
  const write = vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => {
    throw new DOMException("quota", "QuotaExceededError");
  });
  const fetch = vi.fn(async (_path, options) =>
    Response.json({ ...original, ...JSON.parse(options.body).changes }),
  );
  vi.stubGlobal("fetch", fetch);
  const download = vi.fn((_copy: Blob) => "blob:diary-copy");
  vi.stubGlobal("URL", class extends URL {
    static createObjectURL = download;
    static revokeObjectURL = vi.fn();
  });
  vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(() => {});
  render(<NotebookWorkspace context={context} note={original} navigate={vi.fn()} />);
  const editor = screen.getByLabelText("Contenido de prueba");
  fireEvent.change(editor, { target: { value: "Mi primer cambio" } });
  expect(await screen.findByRole("alert")).toHaveTextContent("Puedes seguir editando");
  expect(editor).toBeEnabled();
  expect(screen.queryByRole("button", { name: "Reiniciar con copia" })).toBeNull();
  fireEvent.change(editor, { target: { value: "Mi último cambio" } });
  fireEvent.click(screen.getByRole("button", { name: "Guardar entrada" }));
  await screen.findByText(/No se envió la entrada/);
  expect(fetch).not.toHaveBeenCalled();
  expect(editor).toHaveValue("Mi último cambio");
  expect(localStorage.getItem(id)).toBe(legacy);
  fireEvent.click(screen.getByRole("button", { name: "Descargar borrador" }));
  const copy = await new Promise<DiaryDetail>((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(JSON.parse(String(reader.result)));
    reader.onerror = () => reject(reader.error);
    reader.readAsText(download.mock.calls[0][0]);
  });
  expect(copy.latex_body).toBe("Mi último cambio");

  write.mockRestore();
  fireEvent.click(screen.getByRole("button", { name: "Reintentar conservar borrador" }));
  await waitFor(() => expect(screen.queryByRole("alert")).toBeNull());
  expect(JSON.parse(localStorage.getItem(id)!)).toMatchObject({
    latex_body: "Mi último cambio", pending: "", title: "Copia anterior",
  });
  fireEvent.click(screen.getByRole("button", { name: "Guardar entrada" }));
  await screen.findByText("Entrada guardada y confirmada en esta biblioteca.");
  expect(fetch).toHaveBeenCalledTimes(1);
});
it("does not reconcile an old successful response into a different mounted library", async () => {
  let resolve!: (value: Response) => void;
  const pending = new Promise<Response>((r) => {
    resolve = r;
  });
  const navigate = vi.fn();
  const fetch = vi.fn(() => pending);
  vi.stubGlobal("fetch", fetch);
  let view = render(
    <NotebookWorkspace context={context} note={original} navigate={navigate} />,
  );
  fireEvent.change(screen.getByLabelText("Título de la entrada"), {
    target: { value: "No perder" },
  });
  fireEvent.click(screen.getByRole("button", { name: "Guardar entrada" }));
  await waitFor(() => expect(fetch).toHaveBeenCalledTimes(1));
  view.unmount();
  view = render(
    <NotebookWorkspace
      context={{ ...context, library_id: "other" }}
      note={original}
      navigate={navigate}
    />,
  );
  await act(async () => {
    resolve(Response.json({ ...original, title: "No perder" }));
    await pending;
  });
  expect(screen.getByLabelText("Título de la entrada")).toHaveValue(
    original.title,
  );
  expect(navigate).not.toHaveBeenCalled();
  expect(JSON.parse(localStorage.getItem(key("historical"))!).title).toBe(
    "No perder",
  );
  view.unmount();
});
