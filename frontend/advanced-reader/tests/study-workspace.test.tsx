import {
  act,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { useEffect, useRef } from "react";
import type {
  DocumentEditor,
  EditorSnapshot,
} from "../src/knowledge-map/document-editor";
import { NoteWorkspace } from "../src/study/NoteWorkspace";
import { newStudyDraft, studyVault } from "../src/study/drafts";
import { StudyApp } from "../src/study/StudyApp";
import { createAdvancedReaderApi } from "../src/api/client";
import { studyRequest } from "../src/study/api";
import type { StudyContext } from "../src/study/api";
import type { Intent } from "../src/knowledge-map/model";

vi.mock("../src/pdf/PdfJsController", () => ({
  createPdfJsController: vi.fn(),
}));
// These tests exercise the save/revision boundary. The real catalog selectors
// and citation reads are exercised in the browser against owned MongoDB.
vi.mock("../src/study/SourcePicker", () => ({SourcePicker:()=> <p>Fuente del borrador</p>}));
vi.mock("../src/study/NoteCitation", () => ({NoteCitation:()=> <p>Cita del borrador</p>}));

// Isolate the transport/state boundary. Real mathematical editing and keyboard
// behavior are exercised by the owned Chrome/Firefox traversal and editor tests.
vi.mock("../src/study/DocumentSurface", () => ({
  DocumentContent: ({ content }: { content: string }) => <p>{content}</p>,
  DocumentSurface: ({
    initial,
    changed,
    editorRef,
  }: {
    initial: string;
    changed: (value: string, state: EditorSnapshot) => void;
    editorRef: { current: DocumentEditor | null };
  }) => {
    const value = useRef(initial);
    useEffect(() => {
      editorRef.current = {
        value: () => value.current,
        valid: () => !value.current.includes("unfinished"),
        snapshot: () => ({
          json: { type: "doc" },
          selection: 1,
          scroll: 0,
          sourceMode: false,
        }),
      } as unknown as DocumentEditor;
      return () => {
        editorRef.current = null;
      };
    }, [editorRef]);
    return (
      <textarea
        aria-label="Contenido visual"
        defaultValue={initial}
        onChange={(event) => {
          value.current = event.target.value;
          changed(value.current, {
            json: { type: "doc" },
            selection: 1,
            scroll: 0,
            sourceMode: false,
          });
        }}
      />
    );
  },
}));
const context: StudyContext = {
  library_id: "library-a",
  runtime_id: "runtime-a",
  name: "Biblioteca temporal",
  preparation: {
    state: "ready",
    reason: "",
    version: "v1",
    notes_ready: true,
    reading_ready: true,
  },
};
const body = String.raw`Texto conservado $\frac{1}{2}$ y \begin{legacy}intacto\end{legacy}`;
const response = (value: unknown, status = 200) =>
  new Response(JSON.stringify(value), {
    status,
    headers: { "Content-Type": "application/json" },
  });
const note = (title: string, content: string) => ({
  note_id: "note_123e4567-e89b-42d3-a456-426614174000",
  title,
  body: content,
  source_id: "source-a",
  document_id: null,
  reference_id: null,
  reference_locator: null,
  revision: "confirmed-revision",
  page_start: null,
  page_end: null,
  tags: [],
});

beforeEach(() => {
  localStorage.clear();
  history.replaceState(null, "", "/study");
  vi.unstubAllGlobals();
});

describe("independent note persistence", () => {
  it("keeps a rejected stale edit blocked across reload and offers the current version", async () => {
    const draft={...newStudyDraft("source-a"),title:"Mi nota",content:body,noteId:note("", "").note_id,revision:"old"};
    vi.stubGlobal("fetch",vi.fn(async()=>response({status:"conflict",message:"La nota cambió."})));
    const view=render(<NoteWorkspace context={context} initialDraft={draft} navigate={vi.fn()} notify={vi.fn()}/>);
    fireEvent.click(screen.getByRole("button",{name:"Guardar nota"}));
    await screen.findByRole("button",{name:"Abrir versión guardada; conservar mi borrador"});
    const retained=studyVault(context.library_id).get(draft.id!)!;
    expect(retained.content).toBe(body);expect(retained.revision).toBe("old");
    view.unmount();
    render(<NoteWorkspace context={context} initialDraft={retained} navigate={vi.fn()} notify={vi.fn()}/>);
    expect(screen.getByRole("button",{name:"Guardar nota"})).toBeDisabled();
    expect(screen.getByRole("button",{name:"Abrir versión guardada; conservar mi borrador"})).toBeVisible();
  });
  it("does not adopt a newer revision with a different body after the save acknowledgement", async () => {
    const draft = {...newStudyDraft("source-a"), title:"Mi nota",content:body};
    const navigate=vi.fn(),notify=vi.fn();
    vi.stubGlobal("fetch",vi.fn(async (path:string)=>response(path.endsWith("/operations")
      ? {status:"saved",message:"Nota guardada.",note_id:note("", "").note_id}
      : note("Mi nota","Cambio de otra ventana"))));
    render(<NoteWorkspace context={context} initialDraft={draft} navigate={navigate} notify={notify}/>);
    fireEvent.click(screen.getByRole("button",{name:"Guardar nota"}));
    await screen.findByText(/cambió después del envío/u);
    expect(notify).not.toHaveBeenCalledWith(expect.stringContaining("Nota guardada"));
    expect(navigate).not.toHaveBeenCalled();
    expect(screen.getByLabelText("Contenido visual")).toHaveValue(body);
    const retained=studyVault(context.library_id).get(draft.id!)!;
    expect(retained.content).toBe(body);
    expect(retained.revision).toBe("");
    expect(screen.getByRole("button",{name:"Guardar nota"})).toBeDisabled();
    fireEvent.click(screen.getByRole("button",{name:"Abrir versión guardada; conservar mi borrador"}));
    expect(navigate).toHaveBeenCalledWith("/study/notes/"+note("", "").note_id+"?version=server");
    expect(studyVault(context.library_id).get(draft.id!)!.content).toBe(body);
  });
  it("retains the full draft and the same operation across a lost response, unmount and retry", async () => {
    const payloads: Intent[] = [];
    vi.stubGlobal(
      "fetch",
      vi.fn(async (path: string, init: RequestInit) => {
        if (path.endsWith("/operations")) {
          payloads.push(JSON.parse(init.body as string));
          if (payloads.length === 1) throw new TypeError("Lost response");
          return response({
            status: "saved",
            message: "Nota guardada.",
            note_id: note("", "").note_id,
          });
        }
        return response(note("Nota propia", body));
      }),
    );
    const draft = newStudyDraft("source-a");
    studyVault(context.library_id).put(draft);
    const navigate = vi.fn(),
      notify = vi.fn();
    const view = render(
      <NoteWorkspace
        context={context}
        initialDraft={draft}
        navigate={navigate}
        notify={notify}
      />,
    );
    fireEvent.change(screen.getByLabelText("Nombre de la nota"), {
      target: { value: "Nota propia" },
    });
    fireEvent.change(screen.getByLabelText("Contenido visual"), {
      target: { value: body },
    });
    fireEvent.click(screen.getByRole("button", { name: "Guardar nota" }));
    await screen.findByRole("button", { name: "Reintentar el mismo envío" });
    await waitFor(() =>
      expect(
        screen.getByRole("button", { name: "Reintentar el mismo envío" }),
      ).not.toBeDisabled(),
    );
    expect(notify).not.toHaveBeenCalledWith(expect.stringContaining("Nota guardada"));
    expect(screen.getByLabelText("Contenido visual")).toHaveValue(body);
    view.unmount();
    const recovered = studyVault(context.library_id).get(draft.id!)!;
    render(
      <NoteWorkspace
        context={context}
        initialDraft={recovered}
        navigate={navigate}
        notify={notify}
      />,
    );
    expect(screen.getByLabelText("Nombre de la nota")).toHaveValue(
      "Nota propia",
    );
    fireEvent.click(
      screen.getByRole("button", { name: "Reintentar el mismo envío" }),
    );
    await waitFor(() =>
      expect(notify).toHaveBeenCalledWith(
        expect.stringContaining("Nota guardada."),
      ),
    );
    expect(payloads).toHaveLength(2);
    expect(payloads[1]).toEqual(payloads[0]);
    expect(payloads[0].contenido_latex).toBe(body);
    expect(payloads[0].action).toBe("save_note");
    expect(navigate).toHaveBeenCalledWith(
      "/study/notes/" + note("", "").note_id,
      true,
    );
  });

  it("does not announce saving while the server has not confirmed it", async () => {
    let finish: ((value: Response) => void) | undefined;
    vi.stubGlobal(
      "fetch",
      vi.fn(
        () =>
          new Promise<Response>((resolve) => {
            finish = resolve;
          }),
      ),
    );
    const draft = {
      ...newStudyDraft("source-a"),
      title: "Trabajo",
      content: body,
    };
    const notify = vi.fn();
    render(
      <NoteWorkspace
        context={context}
        initialDraft={draft}
        navigate={vi.fn()}
        notify={notify}
      />,
    );
    fireEvent.click(screen.getByRole("button", { name: "Guardar nota" }));
    expect(screen.getByRole("status")).toHaveTextContent(
      "esperando confirmación",
    );
    expect(notify).not.toHaveBeenCalledWith(expect.stringContaining("Nota guardada"));
    await act(async () =>
      finish!(
        response({
          status: "uncertain",
          message: "No se confirmó la operación.",
        }),
      ),
    );
    expect(screen.getByLabelText("Contenido visual")).toHaveValue(body);
    expect(notify).not.toHaveBeenCalledWith(expect.stringContaining("Nota guardada"));
  });

  it("keeps incomplete mathematics recoverable without sending it to the server", () => {
    const fetch = vi.fn();
    vi.stubGlobal("fetch", fetch);
    const draft = {
      ...newStudyDraft("source-a"),
      title: "En elaboración",
      content: "unfinished formula",
    };
    const vault = studyVault(context.library_id);
    vault.put(draft);
    render(
      <NoteWorkspace
        context={context}
        initialDraft={draft}
        navigate={vi.fn()}
        notify={vi.fn()}
      />,
    );
    fireEvent.click(screen.getByRole("button", { name: "Guardar nota" }));
    expect(screen.getByRole("status")).toHaveTextContent(
      "fórmula está en elaboración",
    );
    expect(vault.get(draft.id!)?.content).toBe("unfinished formula");
    expect(fetch).not.toHaveBeenCalled();
  });

  it("requires compatible preparation and keeps the draft when writes are unavailable", () => {
    const fetch = vi.fn();
    vi.stubGlobal("fetch", fetch);
    const draft = {
      ...newStudyDraft("source-a"),
      title: "Trabajo",
      content: body,
    };
    render(
      <NoteWorkspace
        context={{
          ...context,
          preparation: {
            ...context.preparation,
            state: "unverified",
            notes_ready: false,
          },
        }}
        initialDraft={draft}
        navigate={vi.fn()}
        notify={vi.fn()}
      />,
    );
    fireEvent.click(screen.getByRole("button", { name: "Guardar nota" }));
    expect(screen.getByRole("status")).toHaveTextContent(
      "El borrador se conserva",
    );
    expect(studyVault(context.library_id).get(draft.id!)?.content).toBe(body);
    expect(fetch).not.toHaveBeenCalled();
  });
});

describe("library and scoped HTTP", () => {
  it("finds books by human bibliography and restores the library route through back navigation", async () => {
    history.replaceState(null, "", "/study/library");
    const fetch = vi.fn(async (path: string) =>
      response(
        path.endsWith("/context")
          ? context
          : {
              items: [
                {
                  source_id: "source-a",
                  name: "Álgebra para estudiar",
                  bibliography: [
                    { authors: [{ family: "Noether" }], year: 1930 },
                  ],
                },
              ],
              total: 1,
              page: 1,
            },
      ),
    );
    vi.stubGlobal("fetch", fetch);
    render(<StudyApp />);
    await screen.findByRole("heading", { name: "Tu biblioteca" });
    await screen.findByRole("link", { name: "Álgebra para estudiar" });
    expect(screen.getByText("Noether · 1930")).toBeVisible();
    fireEvent.change(screen.getByRole("searchbox"), {
      target: { value: "Noether" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Buscar" }));
    await waitFor(() => expect(location.search).toBe("?q=Noether"));
    expect(fetch).toHaveBeenCalledWith(
      "/api/study/v1/library?q=Noether&page=1",
      expect.anything(),
    );
    expect(screen.queryByText("document_annotations")).not.toBeInTheDocument();
    await act(async () => {
      history.replaceState(null, "", "/study/library");
      dispatchEvent(new PopStateEvent("popstate"));
    });
    expect(screen.getByRole("searchbox")).toHaveValue("");
  });
  it("keeps library context in requests to the reader and rejects nonlocal API paths", async () => {
    const fetch = vi.fn(async () => response({}));
    vi.stubGlobal("fetch", fetch);
    await createAdvancedReaderApi("library-b").getMetadata(
      "doc_123e4567-e89b-42d3-a456-426614174000",
    );
    expect(
      (fetch.mock.calls[0] as unknown as [string, RequestInit])[1].headers,
    ).toBeInstanceOf(Headers);
    expect(
      new Headers(
        (fetch.mock.calls[0] as unknown as [string, RequestInit])[1].headers,
      ).get("X-MathMongo-Library"),
    ).toBe("library-b");
    await expect(
      studyRequest("https://example.invalid/context", context),
    ).rejects.toThrow("Ruta");
    expect(fetch).toHaveBeenCalledTimes(1);
  });
});
