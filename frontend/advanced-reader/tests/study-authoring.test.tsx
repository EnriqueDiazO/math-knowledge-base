import { mockWindowLocks } from "./web-locks-support";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { act, cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { EditorSnapshot } from "../src/knowledge-map/document-editor";
import { NewSourcePage } from "../src/study/SourceForms";
import { ConceptEditorPage } from "../src/study/ConceptWorkspace";
import type { StudyContext } from "../src/study/api";
import { documentLink } from "../src/security/document-links";

vi.mock("../src/study/DocumentSurface", async () => {
  const React = await import("react");
  return {
    DocumentSurface: ({
      initial,
      changed,
      editorRef,
    }: {
      initial: string;
      changed: (body: string, snapshot: EditorSnapshot) => void;
      editorRef: { current: unknown };
    }) => {
      const content = React.useRef(initial);
      React.useEffect(() => {
        const snapshot = {
          json: { type: "doc" },
          selection: 1,
          scroll: 0,
          sourceMode: false,
        };
        editorRef.current = {
          value: () => content.current,
          snapshot: () => snapshot,
          valid: () => true,
        };
        return () => {
          changed(content.current, snapshot);
          editorRef.current = null;
        };
      }, [editorRef, changed]);
      return (
        <textarea
          aria-label="Contenido de prueba"
          defaultValue={initial}
          onChange={(event) => {
            content.current = event.target.value;
            changed(content.current, {
              json: { type: "doc" },
              selection: 1,
              scroll: 0,
              sourceMode: false,
            });
          }}
        />
      );
    },
  };
});
const context: StudyContext = {
  library_id: "owned",
  runtime_id: "runtime",
  name: "Biblioteca de prueba",
  preparation: {
    state: "ready",
    version: "1",
    reason: "",
    notes_ready: true,
    reading_ready: true,
  },
};
const source = "src_2df041a2-7577-4a78-9e2c-a72740a21fd3";
const requests: { path: string; body: Record<string, unknown> }[] = [];
beforeEach(() => {
  mockWindowLocks();
  localStorage.clear();
  requests.length = 0;
  vi.stubGlobal(
    "fetch",
    vi.fn(async (input, options) => {
      const path = String(input);
      const body = options?.body ? JSON.parse(options.body) : undefined;
      if (body) {
        requests.push({ path, body });
        if (path.endsWith("/sources"))
          return Response.json({ source_id: source });
        if (path.endsWith("/operations"))
          return Response.json({
            status: "saved",
            key: "definition:owned@Fuente de prueba",
          });
      }
      if (path.includes("/catalog/preparation"))
        return Response.json({ state: "ready", version: "1", reason: "" });
      if (path.includes("/library"))
        return Response.json({
          items: [{ source_id: source, name: "Fuente de prueba" }],
          total: 1,
          page: 1,
        });
      if (path.includes("/sources/"))
        return Response.json({
          source_id: source,
          name: "Fuente de prueba",
          references: [],
          documents: [],
        });
      return Response.json(context);
    }),
  );
});
afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  vi.clearAllMocks();
});

describe("authoring operations and recoverable drafts", () => {
  it("sends unchanged category literals intact and leaves the stored citation untouched", async () => {
    const original = globalThis.fetch,
      navigate = vi.fn(),
      user = userEvent.setup();
    const categories = ["Unidad, familia", " propia "];
    vi.stubGlobal(
      "fetch",
      vi.fn(async (input, options) => {
        if (String(input).includes("/concepts/detail?"))
          return Response.json({
            key: "definition:owned@Fuente de prueba",
            id: "definition:owned",
            source: "Fuente de prueba",
            source_id: source,
            titulo: "  Identidad sin normalizar  ",
            tipo: "definicion",
            contenido_latex: "Texto original.",
            categorias: categories,
            comentario: "",
            reference_id: "ref_2df041a2-7577-4a78-9e2c-a72740a21fd3",
            reference_locator: null,
            revision: "revision-original",
            passages: [],
          });
        return original(input, options);
      }),
    );
    render(
      <ConceptEditorPage
        context={context}
        navigate={navigate}
        search=""
        conceptKey="definition:owned@Fuente de prueba"
      />,
    );
    await screen.findByLabelText("Nombre del concepto");
    await user.click(screen.getByRole("button", { name: "Guardar concepto" }));
    await waitFor(() => expect(navigate).toHaveBeenCalled());
    expect(requests[0].body).toMatchObject({
      titulo: "  Identidad sin normalizar  ",
      categorias: categories,
      contenido_latex: "Texto original.",
      revision: "revision-original",
    });
    expect(requests[0].body).not.toHaveProperty("reference_id");
    expect(requests[0].body).not.toHaveProperty("reference_locator");
  });
  it("keeps an old library's pending source and ignores its late reply after unmount", async () => {
    const user = userEvent.setup(),
      navigate = vi.fn();
    const original = globalThis.fetch;
    let confirm!: (response: Response) => void;
    vi.stubGlobal(
      "fetch",
      vi.fn(async (input, options) => {
        if (String(input).endsWith("/sources"))
          return new Promise<Response>((resolve) => {
            confirm = resolve;
          });
        return original(input, options);
      }),
    );
    let app = render(
      <NewSourcePage context={context} navigate={navigate} search="" />,
    );
    await user.type(
      screen.getByLabelText("Nombre de la fuente"),
      "Fuente de biblioteca anterior",
    );
    await user.click(screen.getByRole("button", { name: "Guardar fuente" }));
    await screen.findByRole("button", { name: "Guardando fuente…" });
    app.unmount();
    app = render(
      <NewSourcePage
        context={{
          ...context,
          library_id: "another",
          runtime_id: "new-runtime",
        }}
        navigate={navigate}
        search=""
      />,
    );
    await act(async () => {
      confirm(Response.json({ source_id: source }));
    });
    await waitFor(() =>
      expect(screen.getByLabelText("Nombre de la fuente")).toHaveValue(""),
    );
    expect(navigate).not.toHaveBeenCalled();
    expect(
      JSON.parse(localStorage.getItem("mathmongo-source-v1-owned")!).pending,
    ).toBe(true);
    expect(localStorage.getItem("mathmongo-source-v1-another")).toBeNull();
    app.unmount();
  });
  it("replays the identical source request after a lost acknowledgement and reload", async () => {
    const user = userEvent.setup(),
      navigate = vi.fn();
    const fetch = globalThis.fetch;
    vi.stubGlobal(
      "fetch",
      vi.fn(async (input, options) => {
        if (String(input).endsWith("/sources")) {
          const body = JSON.parse(String(options?.body));
          requests.push({ path: String(input), body });
          if (requests.length === 1)
            throw new TypeError("lost acknowledgement");
          return Response.json({ source_id: source });
        }
        return fetch(input, options);
      }),
    );
    let app = render(
      <NewSourcePage context={context} navigate={navigate} search="" />,
    );
    await user.type(
      screen.getByLabelText("Nombre de la fuente"),
      "Una fuente conservada",
    );
    await user.click(screen.getByRole("button", { name: "Guardar fuente" }));
    await screen.findByRole("button", { name: "Reintentar el mismo envío" });
    app.unmount();
    app = render(
      <NewSourcePage context={context} navigate={navigate} search="" />,
    );
    expect(screen.getByLabelText("Nombre de la fuente")).toHaveValue(
      "Una fuente conservada",
    );
    await user.click(
      screen.getByRole("button", { name: "Reintentar el mismo envío" }),
    );
    await waitFor(() =>
      expect(navigate).toHaveBeenCalledWith("/study/sources/" + source),
    );
    expect(requests).toHaveLength(2);
    expect(requests[1].body).toEqual(requests[0].body);
    app.unmount();
  });
  it("keeps unreadable source storage intact and offers an explicit archived restart", async () => {
    const user = userEvent.setup(),
      key = "mathmongo-source-v1-owned",
      raw = "{unreadable original";
    localStorage.setItem(key, raw);
    render(<NewSourcePage context={context} navigate={vi.fn()} search="" />);
    await user.type(
      screen.getByLabelText("Nombre de la fuente"),
      "Nuevo texto",
    );
    await user.click(screen.getByRole("button", { name: "Guardar fuente" }));
    expect(requests).toHaveLength(0);
    expect(localStorage.getItem(key)).toBe(raw);
    await user.click(
      screen.getByRole("button", {
        name: "Conservar copia y empezar otra ficha",
      }),
    );
    expect(
      Object.keys(localStorage)
        .filter((k) => k.startsWith(key + "-archive-"))
        .map((k) => localStorage.getItem(k)),
    ).toEqual([raw]);
    expect(screen.getByLabelText("Nombre de la fuente")).toHaveValue("");
  });
  it("retains prose across metadata edits and does not resurrect the confirmed pending draft on unmount", async () => {
    const user = userEvent.setup(),
      navigate = vi.fn();
    let app = render(
      <ConceptEditorPage
        context={context}
        navigate={navigate}
        search={"?source=" + source}
      />,
    );
    await user.type(
      screen.getByLabelText("Nombre del concepto"),
      "Idea inicial",
    );
    await user.type(
      screen.getByLabelText("Contenido de prueba"),
      "Texto con una fórmula conservada.",
    );
    await user.clear(screen.getByLabelText("Nombre del concepto"));
    await user.type(
      screen.getByLabelText("Nombre del concepto"),
      "Idea renombrada",
    );
    expect(
      JSON.parse(
        localStorage.getItem(
          "mathmongo-drafts-v2-owned-study-concepts-window-" +
            sessionStorage.getItem("mathmongo-concept-window-v1"),
        )!,
      ).new.content,
    ).toBe("Texto con una fórmula conservada.");
    await user.click(screen.getByRole("button", { name: "Guardar concepto" }));
    await waitFor(() =>
      expect(navigate).toHaveBeenCalledWith(
        "/study/concepts/definition%3Aowned%40Fuente%20de%20prueba",
      ),
    );
    expect(requests[0].body).toMatchObject({
      titulo: "Idea renombrada",
      contenido_latex: "Texto con una fórmula conservada.",
      source_id: source,
    });
    app.unmount();
    expect(
      JSON.parse(
        localStorage.getItem(
          "mathmongo-drafts-v2-owned-study-concepts-window-" +
            sessionStorage.getItem("mathmongo-concept-window-v1"),
        )!,
      ),
    ).toEqual({});
    app = render(
      <ConceptEditorPage context={context} navigate={navigate} search="" />,
    );
    await waitFor(() =>
      expect(screen.getByLabelText("Nombre del concepto")).toBeEnabled(),
    );
    expect(screen.getByLabelText("Nombre del concepto")).toHaveValue("");
    app.unmount();
  });
  it("does not turn executable or credential-bearing academic destinations into links", () => {
    expect(documentLink("https://example.org/paper")).toBe(
      "https://example.org/paper",
    );
    for (const value of [
      "javascript:alert(1)",
      "data:text/html,unsafe",
      "https://name:password@example.org/",
      "https://example.org/\nredirect",
      "file:///etc/passwd",
    ])
      expect(documentLink(value)).toBeUndefined();
  });
});
