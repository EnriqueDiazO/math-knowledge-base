import { useEffect, useRef } from "react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import {
  act,
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import type {
  DocumentEditor,
  EditorSnapshot,
} from "../src/knowledge-map/document-editor";
import { StructuredWorkspace } from "../src/study/StructuredWorkspace";
import { StructuredPages } from "../src/study/StructuredPages";
import {
  regions,
  structuredDraft,
  structuredValues,
  structuredRequest,
  sameStructuredValue,
  orderedPages,
  type Family,
  type StructuredDetail,
} from "../src/study/structured-state";
import type { StudyContext } from "../src/study/api";

vi.mock("../src/study/DocumentSurface", () => ({
  DocumentSurface: ({
    initial,
    changed,
    editorRef,
  }: {
    initial: string;
    changed: (value: string, state: EditorSnapshot) => void;
    editorRef: { current: DocumentEditor | null };
  }) => {
    const value = useRef(initial),
      onChange = useRef(changed);
    onChange.current = changed;
    const snapshot = {
      json: { type: "doc" },
      selection: 1,
      scroll: 0,
      sourceMode: true,
    };
    useEffect(() => {
      editorRef.current = {
        value: () => value.current,
        snapshot: () => snapshot,
        valid: () => !value.current.includes("unfinished"),
      } as unknown as DocumentEditor;
      return () => {
        onChange.current(value.current, snapshot);
        editorRef.current = null;
      };
      // This adapter models the imperative editor lifecycle; browsers exercise real MathLive.
      // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [editorRef]);
    return (
      <textarea
        aria-label="Región de prueba"
        defaultValue={initial}
        onChange={(event) => {
          value.current = event.target.value;
          onChange.current(value.current, snapshot);
        }}
      />
    );
  },
}));
vi.mock("../src/study/StructuredReferences", () => ({
  StructuredReferences: ({ insert }: { insert: (latex: string) => void }) => (
    <button onClick={() => insert("Cita canónica")}>
      Insertar cita de prueba
    </button>
  ),
}));
const context = { library_id: "owned", runtime_id: "runtime" } as StudyContext;
const click = (name: string) =>
  fireEvent.click(screen.getByRole("button", { name }));
const fill = (label: string, value: string) =>
  fireEvent.change(screen.getByLabelText(label, { exact: true }), {
    target: { value },
  });
function note(family: Family): StructuredDetail {
  const draft = structuredDraft(family),
    value = structuredValues(draft, family);
  return {
    note_id: "saved",
    revision: "a".repeat(64),
    family,
    metadata: { title: "Original" },
    document: value.document,
    latex_body: "Fuente exacta",
  };
}
beforeEach(() => localStorage.clear());
afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});
for (const family of ["cornell", "cpi"] as const) {
  const title = family === "cornell" ? "Cornell" : "CPI";
  it(
    family +
      ": no-op keeps missing metadata, extensions and source outside the visual projection",
    () => {
      const original = note(family);
      original.document.custom = { keep: true };
      const draft = structuredDraft(family, original);
      expect(structuredRequest(draft, family, true)).toMatchObject({
        revision: original.revision,
        metadata: {},
        document: original.document,
      });
      expect(structuredValues(draft, family).metadata).not.toHaveProperty(
        "date",
      );
      expect(
        orderedPages(
          [...original.document.pages, ...original.document.pages],
          family,
        ).map((page) => page.order ?? page.page_number),
      ).toEqual([1, 2]);
    },
  );
  it(
    family +
      ": switches regions without editor cleanup overwriting the next region and recovers every draft",
    () => {
      const props = { context, family, navigate: vi.fn() };
      const view = render(<StructuredWorkspace {...props} />);
      fill("Título de la nota", "Conservar regiones");
      fill("Región de prueba", String.raw`\macroDesconocida{α}`);
      click(regions[family][1][1]);
      expect(screen.getByLabelText("Región de prueba")).toHaveValue("");
      fill("Región de prueba", "Desarrollo independiente");
      click(regions[family][0][1]);
      expect(screen.getByLabelText("Región de prueba")).toHaveValue(
        String.raw`\macroDesconocida{α}`,
      );
      view.unmount();
      render(<StructuredWorkspace {...props} />);
      expect(screen.getByLabelText("Título de la nota")).toHaveValue(
        "Conservar regiones",
      );
      expect(screen.getByLabelText("Región de prueba")).toHaveValue(
        String.raw`\macroDesconocida{α}`,
      );
      click(regions[family][1][1]);
      expect(screen.getByLabelText("Región de prueba")).toHaveValue(
        "Desarrollo independiente",
      );
      fill("Región de prueba", "unfinished");
      click(regions[family][2][1]);
      expect(screen.getByText(/Completa la fórmula antes/)).toBeVisible();
      expect(screen.getByLabelText("Región de prueba")).toHaveValue(
        "unfinished",
      );
    },
  );
  it(
    family +
      ": page duplication, order and explicit removal preserve the retained page",
    () => {
      render(
        <StructuredWorkspace
          context={context}
          family={family}
          navigate={vi.fn()}
        />,
      );
      fill("Región de prueba", "Primera");
      click("Duplicar página");
      expect(screen.getByLabelText("Región de prueba")).toHaveValue("Primera");
      fill("Región de prueba", "Segunda");
      click("Mover página antes");
      click("Página 2");
      expect(screen.getByLabelText("Región de prueba")).toHaveValue("Primera");
      click("Mover página antes");
      click("Mover página después");
      click("Retirar página");
      click("Conservar página");
      expect(screen.getByRole("button", { name: "Página 2" })).toBeVisible();
      click("Retirar página");
      click("Confirmar retirada de esta página");
      expect(screen.getByLabelText("Región de prueba")).toHaveValue("Segunda");
      click("Añadir página");
      expect(screen.getByLabelText("Región de prueba")).toHaveValue("");
      click("Insertar cita de prueba");
      expect(screen.getByLabelText("Región de prueba")).toHaveValue(
        "\n\nCita canónica",
      );
    },
  );
  it(
    family +
      ": a lost response retains exactly the same creation request across reload",
    async () => {
      const calls: unknown[] = [],
        navigate = vi.fn();
      let fail = true;
      vi.stubGlobal(
        "fetch",
        vi.fn(async (_path, options) => {
          const body = JSON.parse(options.body);
          calls.push(body);
          if (fail) throw new Error("Respuesta perdida");
          return Response.json({
            note_id: family + "_created",
            revision: "b".repeat(64),
            family,
            metadata: body.metadata,
            document: body.document,
            latex_body: "Confirmada",
          });
        }),
      );
      const view = render(
        <StructuredWorkspace
          context={context}
          family={family}
          navigate={navigate}
        />,
      );
      fill("Título de la nota", "Recuperable");
      fill("Región de prueba", "Región exacta");
      click("Guardar nota " + title);
      await screen.findByText(/No se confirmó la conexión/);
      view.unmount();
      fail = false;
      render(
        <StructuredWorkspace
          context={context}
          family={family}
          navigate={navigate}
        />,
      );
      click("Reintentar el mismo guardado");
      await waitFor(() =>
        expect(navigate).toHaveBeenCalledWith(
          "/study/notebook/" + family + "/" + family + "_created",
        ),
      );
      expect(calls).toHaveLength(2);
      expect(calls[0]).toEqual(calls[1]);
      expect(
        localStorage.getItem(
          "mathmongo-structured-v1-owned-" + family + "-new",
        ),
      ).toBeNull();
    },
  );
  it(
    family +
      ": stale success cannot confirm a different body or an unmounted library",
    async () => {
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
        <StructuredWorkspace
          context={context}
          family={family}
          navigate={navigate}
        />,
      );
      fill("Título de la nota", "Mi nota");
      click("Guardar nota " + title);
      await act(async () => resolve(Response.json(note(family))));
      expect(screen.getByText(/El contenido no se confirmó/)).toBeVisible();
      expect(navigate).not.toHaveBeenCalled();
      click("Reintentar el mismo guardado");
      view.unmount();
      await act(async () => resolve(Response.json(note(family))));
      expect(navigate).not.toHaveBeenCalled();
      expect(localStorage.length).toBe(1);
    },
  );
  it(
    family +
      ": conflicting edit keeps local regions until an explicitly archived recovery",
    async () => {
      const original = note(family),
        remote = {
          ...original,
          metadata: { title: "Remota" },
          revision: "b".repeat(64),
        };
      vi.stubGlobal(
        "fetch",
        vi.fn(async (_path, options) =>
          options.method === "POST"
            ? Response.json(
                {
                  error: { code: "catalog_conflict", message: "Otra ventana" },
                },
                { status: 409 },
              )
            : Response.json(remote),
        ),
      );
      render(
        <StructuredWorkspace
          context={context}
          family={family}
          navigate={vi.fn()}
          note={original}
        />,
      );
      fill("Región de prueba", "Trabajo local");
      click("Guardar nota " + title);
      await screen.findByText("Otra ventana");
      expect(screen.getByLabelText("Región de prueba")).toHaveValue(
        "Trabajo local",
      );
      click("Consultar versión guardada");
      await screen.findByRole("button", {
        name: "Archivar borrador y abrir versión guardada",
      });
      click("Archivar borrador y abrir versión guardada");
      expect(screen.getByLabelText("Título de la nota")).toHaveValue("Remota");
      const archive = Object.keys(localStorage).find((key) =>
        key.includes("-archive-"),
      );
      expect(archive).toBeDefined();
      expect(localStorage.getItem(archive!)).toContain("Trabajo local");
    },
  );
  it(
    family + ": lists summaries and opens the dedicated activity",
    async () => {
      vi.stubGlobal(
        "fetch",
        vi.fn(async () =>
          Response.json({
            items: [{ note_id: "one", title: "Nota recuperada" }],
            total: 21,
            page: 1,
          }),
        ),
      );
      const navigate = vi.fn();
      render(
        <StructuredPages
          context={context}
          family={family}
          identity=""
          search=""
          navigate={navigate}
        />,
      );
      expect(
        await screen.findByRole("link", { name: "Nota recuperada" }),
      ).toHaveAttribute("href", "/study/notebook/" + family + "/one");
      click("Siguientes");
      expect(navigate).toHaveBeenCalledWith(
        "/study/notebook/" + family + "?page=2",
      );
    },
  );
}
it("rejects damaged nested drafts and compares JSON values independent of key order", () => {
  const draft = structuredDraft("cornell");
  expect(
    sameStructuredValue({ a: [1, 2], b: null }, { b: null, a: [1, 2] }),
  ).toBe(true);
  expect(sameStructuredValue([1], { 0: 1 })).toBe(false);
  expect(sameStructuredValue(null, {})).toBe(false);
  expect(sameStructuredValue([1], [2])).toBe(false);
  expect(sameStructuredValue({ a: 1 }, { a: 1, b: 2 })).toBe(false);
  for (const [key, value] of Object.entries({
    document: "{}",
    keys: "[]",
    origins: "[]",
    snapshots: "[]",
  }))
    expect(() =>
      structuredValues({ ...draft, [key]: value }, "cornell"),
    ).toThrow();
  const value = structuredValues(draft, "cornell");
  value.document.pages[0].main = { latex: 1, heading: "Invalid" };
  expect(() =>
    structuredValues(
      { ...draft, document: JSON.stringify(value.document) },
      "cornell",
    ),
  ).toThrow();
  expect(() =>
    structuredRequest({ ...draft, original: "null" }, "cornell", true),
  ).toThrow();
});
