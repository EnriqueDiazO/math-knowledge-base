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
const buffered = { source: undefined as string | undefined };

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
    const field = useRef<HTMLTextAreaElement>(null);
    const regionElement = useRef<Element | null>(null);
    const activeValue = () =>
      !regionElement.current ||
      regionElement.current.getAttribute("data-active") === "true"
        ? (buffered.source ?? value.current)
        : value.current;
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
      regionElement.current = field.current?.closest(".cornell-region") ?? null;
      editorRef.current = {
        value: activeValue,
        insertLatex: (latex: string) => {
          value.current += latex;
          if (field.current) field.current.value = value.current;
          onChange.current(value.current, snapshot);
          return true;
        },
        snapshot: () => snapshot,
        valid: () => !value.current.includes("unfinished"),
      } as unknown as DocumentEditor;
      return () => {
        onChange.current(activeValue(), snapshot);
        editorRef.current = null;
      };
      // This adapter models the imperative editor lifecycle; browsers exercise real MathLive.
      // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [editorRef]);
    return (
      <textarea
        ref={field}
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
const activeRegion = () =>
  (document.querySelector(
    '.cornell-region[data-active="true"] textarea[aria-label="Región de prueba"]',
  ) ||
    screen.getByLabelText("Región de prueba", {
      exact: true,
    })) as HTMLTextAreaElement;
const fill = (label: string, value: string) =>
  fireEvent.change(
    label === "Región de prueba"
      ? activeRegion()
      : screen.getByLabelText(label, { exact: true }),
    {
      target: { value },
    },
  );
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
beforeEach(() => {
  localStorage.clear();
  buffered.source = undefined;
});
afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});
for (const family of ["cornell", "cpi"] as const) {
  const title = family === "cornell" ? "Cornell" : "CPI";
  it(
    family +
      ": preserves the existing image resource while saving automatic attribution and watermark placement",
    async () => {
      const original = note(family);
      original.document.watermark = {
        ...(original.document.watermark as object),
        type: "image",
        image_id: "shared-original",
        private_extension: "keep",
      };
      const calls: Record<string, unknown>[] = [];
      vi.stubGlobal(
        "fetch",
        vi.fn(async (_path, options) => {
          const body = JSON.parse(options.body);
          calls.push(body);
          return Response.json({
            ...original,
            revision: "b".repeat(64),
            metadata: { ...original.metadata, ...body.metadata },
            document: body.document,
            latex_body: "Confirmada",
          });
        }),
      );
      render(
        <StructuredWorkspace
          context={context}
          family={family}
          note={original}
          navigate={vi.fn()}
        />,
      );
      fireEvent.click(screen.getByText("Pie de página y marca de agua"));
      expect(screen.queryByLabelText("Texto de la marca de agua")).toBeNull();
      fireEvent.click(screen.getByLabelText("Incluir pie de página"));
      fill("Autor del pie", "Autora propia");
      fill("Curso del pie", "Curso conservado");
      fill("Año del pie", "2026");
      fill("Posición del pie", "top_right");
      fill("Posición de la marca", "bottom_right");
      fill("Escala de la marca", "0.8");
      fireEvent.click(screen.getByLabelText("Marca en todas las páginas"));
      expect(calls).toHaveLength(0);
      click("Guardar nota " + title);
      await screen.findByText("Nota guardada y confirmada en esta biblioteca.");
      expect(calls).toHaveLength(1);
      expect(calls[0].document).toMatchObject({
        attribution: {
          enabled: true,
          mode: "auto",
          author: "Autora propia",
          course: "Curso conservado",
          year: "2026",
          position: "top_right",
        },
        watermark: {
          type: "image",
          image_id: "shared-original",
          private_extension: "keep",
          all_pages: false,
          scale: 0.8,
          position: "bottom_right",
        },
        pages: original.document.pages,
      });
    },
  );
  it(
    family +
      ": editorial changes flush pending source, preserve opaque fields and recover without saving",
    async () => {
      const original = note(family);
      original.document.watermark = {
        ...(original.document.watermark as object),
        private_extension: { keep: true },
      };
      const props = { context, family, note: original, navigate: vi.fn() };
      const view = render(<StructuredWorkspace {...props} />);
      // Model an imperative editor change whose snapshot has not reached React yet.
      buffered.source = String.raw`\unknown{Texto íntegro y á}`;
      fill("Título de la región", "Región renombrada");
      fireEvent.click(screen.getByText("Pie de página y marca de agua"));
      fireEvent.click(screen.getByLabelText("Incluir pie de página"));
      fill("Contenido del pie", "custom");
      fill("Texto del pie", "Autoría propia");
      fireEvent.click(screen.getByLabelText("Incluir marca de agua"));
      fill("Texto de la marca de agua", "ESTUDIO");
      fill("Opacidad de la marca", "0");
      const read = () =>
        structuredValues(
          JSON.parse(
            localStorage.getItem(
              "mathmongo-structured-v1-owned-" + family + "-saved",
            )!,
          ),
          family,
        ).document;
      const document = read();
      expect(document.pages[0][regions[family][0][0]]).toMatchObject({
        heading: "Región renombrada",
        latex: buffered.source,
      });
      expect(document.pages[0][regions[family][1][0]]).toEqual(
        original.document.pages[0][regions[family][1][0]],
      );
      expect(document.attribution).toMatchObject({
        enabled: true,
        mode: "custom",
        text: "Autoría propia",
      });
      expect(document.watermark).toMatchObject({
        enabled: true,
        text: "ESTUDIO",
        opacity: 0,
        private_extension: { keep: true },
      });
      view.unmount();
      buffered.source = undefined;
      render(<StructuredWorkspace {...props} />);
      expect(activeRegion()).toHaveValue(
        String.raw`\unknown{Texto íntegro y á}`,
      );
      fireEvent.click(screen.getByText("Pie de página y marca de agua"));
      expect(screen.getByLabelText("Texto del pie")).toHaveValue(
        "Autoría propia",
      );
      expect(read()).toEqual(document);
    },
  );
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
      expect(activeRegion()).toHaveValue("");
      fill("Región de prueba", "Desarrollo independiente");
      click(regions[family][0][1]);
      expect(activeRegion()).toHaveValue(String.raw`\macroDesconocida{α}`);
      view.unmount();
      render(<StructuredWorkspace {...props} />);
      expect(screen.getByLabelText("Título de la nota")).toHaveValue(
        "Conservar regiones",
      );
      expect(activeRegion()).toHaveValue(String.raw`\macroDesconocida{α}`);
      click(regions[family][1][1]);
      expect(activeRegion()).toHaveValue("Desarrollo independiente");
      fill("Región de prueba", "unfinished");
      click(regions[family][2][1]);
      expect(screen.getByText(/Completa la fórmula antes/)).toBeVisible();
      expect(activeRegion()).toHaveValue("unfinished");
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
      expect(activeRegion()).toHaveValue("Primera");
      fill("Región de prueba", "Segunda");
      click("Mover página antes");
      click("Página 2");
      expect(activeRegion()).toHaveValue("Primera");
      click("Mover página antes");
      click("Mover página después");
      click("Retirar página");
      click("Conservar página");
      expect(screen.getByRole("button", { name: "Página 2" })).toBeVisible();
      click("Retirar página");
      click("Confirmar retirada de esta página");
      expect(activeRegion()).toHaveValue("Segunda");
      click("Añadir página");
      expect(activeRegion()).toHaveValue("");
      click("Insertar cita de prueba");
      expect(activeRegion()).toHaveValue(
        family === "cornell" ? "Cita canónica" : "\n\nCita canónica",
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
      expect(activeRegion()).toHaveValue("Trabajo local");
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
      expect(
        screen.getByRole("button", { name: "Buscar notas" }),
      ).toHaveAttribute("type", "submit");
      click("Siguientes");
      expect(navigate).toHaveBeenCalledWith(
        "/study/notebook/" + family + "?page=2",
      );
    },
  );
  it(
    family +
      ": preserves metadata, template and region heading across draft recovery",
    () => {
      const view = render(
        <StructuredWorkspace
          context={context}
          family={family}
          navigate={vi.fn()}
        />,
      );
      fill("Título de la nota", "Metadatos recuperables");
      fireEvent.click(screen.getByText("Fecha, proyecto y etiquetas"));
      fill("Fecha de la nota", "2024-02-29");
      fill("Proyecto", "Álgebra");
      fill("Contexto", "investigación");
      fill("Etiquetas (una por línea)", "coma, literal\nsegunda");
      fill("Plantilla de la nota", family + "_hybrid_compact_v1");
      fill("Título de la región", "Pregunta propia");
      view.unmount();
      render(
        <StructuredWorkspace
          context={context}
          family={family}
          navigate={vi.fn()}
        />,
      );
      expect(screen.getByLabelText("Título de la región")).toHaveValue(
        "Pregunta propia",
      );
      expect(screen.getByLabelText("Proyecto")).toHaveValue("Álgebra");
      expect(screen.getByLabelText("Contexto")).toHaveValue("investigación");
      expect(screen.getByLabelText("Fecha de la nota")).toHaveValue(
        "2024-02-29",
      );
      expect(screen.getByLabelText("Etiquetas (una por línea)")).toHaveValue(
        "coma, literal\nsegunda",
      );
      expect(screen.getByLabelText("Plantilla de la nota")).toHaveValue(
        family + "_hybrid_compact_v1",
      );
    },
  );
  it(
    family + ": searches literal text and returns to previous summary pages",
    async () => {
      const fetch = vi.fn(async (_path: unknown) =>
        Response.json({ items: [{ note_id: "untitled" }], total: 21, page: 2 }),
      );
      vi.stubGlobal("fetch", fetch);
      const navigate = vi.fn();
      render(
        <StructuredPages
          context={context}
          family={family}
          identity=""
          search="?page=2&q=anterior"
          navigate={navigate}
        />,
      );
      expect(
        await screen.findByRole("link", { name: "Nota sin título" }),
      ).toHaveAttribute("href", "/study/notebook/" + family + "/untitled");
      expect(screen.getByRole("button", { name: "Siguientes" })).toBeDisabled();
      expect(String(fetch.mock.calls[0]?.[0])).toContain("page=2");
      click("Anteriores");
      expect(navigate).toHaveBeenLastCalledWith(
        "/study/notebook/" + family + "?page=1&q=anterior",
      );
      fill("Buscar notas " + title, "Texto [literal]");
      click("Buscar notas");
      const url = new URL(navigate.mock.calls.at(-1)![0], "http://localhost");
      expect(url.searchParams.get("q")).toBe("Texto [literal]");
      expect(url.searchParams.has("page")).toBe(false);
    },
  );
  it(family + ": failed listing retries without creating a note", async () => {
    let failed = true;
    const fetch = vi.fn(async () =>
      failed
        ? Response.json(
            { error: { message: "Consulta no disponible" } },
            { status: 503 },
          )
        : Response.json({ items: [], total: 0, page: 1 }),
    );
    vi.stubGlobal("fetch", fetch);
    render(
      <StructuredPages
        context={context}
        family={family}
        identity=""
        search=""
        navigate={vi.fn()}
      />,
    );
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Consulta no disponible",
    );
    failed = false;
    click("Reintentar búsqueda");
    await screen.findByText(/Todavía no hay notas/);
    expect(fetch).toHaveBeenCalledTimes(2);
    expect(screen.queryByLabelText("Título de la nota")).toBeNull();
  });
  it(
    family +
      ": refuses an incompatible detail until its explicit retry succeeds",
    async () => {
      const original = note(family);
      let failed = true;
      vi.stubGlobal(
        "fetch",
        vi.fn(async () =>
          failed
            ? Response.json(
                { error: { message: "Esta nota pertenece a otra actividad" } },
                { status: 409 },
              )
            : Response.json(original),
        ),
      );
      render(
        <StructuredPages
          context={context}
          family={family}
          identity="saved"
          search=""
          navigate={vi.fn()}
        />,
      );
      expect(await screen.findByRole("alert")).toHaveTextContent(
        "otra actividad",
      );
      expect(screen.queryByLabelText("Título de la nota")).toBeNull();
      failed = false;
      click("Reintentar nota");
      expect(await screen.findByLabelText("Título de la nota")).toHaveValue(
        "Original",
      );
    },
  );
  it(
    family +
      ": archives an unreadable draft before restarting a new structured document",
    () => {
      const key = "mathmongo-structured-v1-owned-" + family + "-new",
        corrupt = JSON.stringify({
          ...structuredDraft(family),
          document: "{}",
        });
      localStorage.setItem(key, corrupt);
      render(
        <StructuredWorkspace
          context={context}
          family={family}
          navigate={vi.fn()}
        />,
      );
      expect(screen.getByRole("alert")).toHaveTextContent(
        "estructura del borrador no es válida",
      );
      expect(screen.queryByLabelText("Región de prueba")).toBeNull();
      click("Reiniciar con copia");
      expect(activeRegion()).toHaveValue("");
      const archive = Object.keys(localStorage).find((item) =>
        item.startsWith(key + "-archive-"),
      );
      expect(archive).toBeDefined();
      expect(localStorage.getItem(archive!)).toBe(corrupt);
    },
  );
  it(
    family +
      ": storage failure preserves the in-memory draft and prevents an unprotected save",
    () => {
      const fetch = vi.fn();
      vi.stubGlobal("fetch", fetch);
      render(
        <StructuredWorkspace
          context={context}
          family={family}
          navigate={vi.fn()}
        />,
      );
      const write = vi
        .spyOn(Storage.prototype, "setItem")
        .mockImplementation(() => {
          throw new DOMException("quota", "QuotaExceededError");
        });
      try {
        fill("Título de la nota", "Trabajo en memoria");
        expect(screen.getByRole("alert")).toHaveTextContent(
          "navegador no pudo conservar",
        );
        expect(screen.getByLabelText("Título de la nota")).toHaveValue(
          "Trabajo en memoria",
        );
        expect(
          screen.getByRole("button", { name: "Guardar nota " + title }),
        ).toBeDisabled();
        expect(fetch).not.toHaveBeenCalled();
      } finally {
        write.mockRestore();
      }
    },
  );
  it(
    family +
      ": a validation rejection unlocks correction and does not claim a saved note",
    async () => {
      const navigate = vi.fn(),
        calls: Record<string, unknown>[] = [];
      vi.stubGlobal(
        "fetch",
        vi.fn(async (_path, options) => {
          const body = JSON.parse(options.body);
          calls.push(body);
          return calls.length === 1
            ? Response.json(
                {
                  error: {
                    code: "invalid_study_request",
                    message: "Revisa el título demasiado largo",
                  },
                },
                { status: 422 },
              )
            : Response.json({
                ...note(family),
                metadata: body.metadata,
                document: body.document,
              });
        }),
      );
      render(
        <StructuredWorkspace
          context={context}
          family={family}
          navigate={navigate}
        />,
      );
      fill("Título de la nota", "x".repeat(501));
      fill("Región de prueba", "Contenido conservado");
      click("Guardar nota " + title);
      await screen.findByText("Revisa el título demasiado largo");
      expect(navigate).not.toHaveBeenCalled();
      expect(activeRegion()).toHaveValue("Contenido conservado");
      fill("Título de la nota", "Título corregido");
      click("Guardar nota " + title);
      await waitFor(() =>
        expect(navigate).toHaveBeenCalledWith(
          "/study/notebook/" + family + "/saved",
        ),
      );
      expect(calls[0].request_id).toBe(calls[1].request_id);
      expect(calls[0]).not.toEqual(calls[1]);
    },
  );
  it(
    family +
      ": metadata editing preserves an explicit historical template and advances the observed revision",
    async () => {
      const original = note(family);
      original.document.template_id = "personal-historical-template";
      const calls: Record<string, unknown>[] = [];
      vi.stubGlobal(
        "fetch",
        vi.fn(async (_path, options) => {
          const body = JSON.parse(options.body);
          calls.push(body);
          return Response.json({
            ...original,
            metadata: { ...original.metadata, ...body.metadata },
            revision: "b".repeat(64),
          });
        }),
      );
      render(
        <StructuredWorkspace
          context={context}
          family={family}
          note={original}
          navigate={vi.fn()}
        />,
      );
      expect(screen.getByLabelText("Plantilla de la nota")).toHaveValue(
        "personal-historical-template",
      );
      fill("Título de la nota", "Sólo el título");
      click("Guardar nota " + title);
      await screen.findByText("Nota guardada y confirmada en esta biblioteca.");
      expect(calls[0].metadata).toEqual({ title: "Sólo el título" });
      expect(calls[0].document).toEqual(original.document);
      const saved = JSON.parse(
        localStorage.getItem(
          "mathmongo-structured-v1-owned-" + family + "-saved",
        )!,
      );
      expect(saved.revision).toBe("b".repeat(64));
      expect(saved.pending).toBe("");
    },
  );
  it(
    family + ": no-op historical saves do not invent a missing title or date",
    async () => {
      const original = note(family);
      original.metadata = {};
      const fetch = vi.fn(async (_path, options) => {
        expect(JSON.parse(options.body).metadata).toEqual({});
        return Response.json(original);
      });
      vi.stubGlobal("fetch", fetch);
      render(
        <StructuredWorkspace
          context={context}
          family={family}
          note={original}
          navigate={vi.fn()}
        />,
      );
      click("Guardar nota " + title);
      await screen.findByText("Nota guardada y confirmada en esta biblioteca.");
      expect(fetch).toHaveBeenCalledTimes(1);
      expect(screen.getByLabelText("Título de la nota")).toHaveValue("");
    },
  );
  it(
    family +
      ": the page limit prevents adding or duplicating beyond the accepted document",
    () => {
      const original = note(family),
        first = original.document.pages[0];
      original.document.pages = Array.from({ length: 30 }, (_, index) => ({
        ...structuredClone(first),
        ...(family === "cornell"
          ? { page_id: "page-" + index, order: index + 1 }
          : { page_number: index + 1 }),
      }));
      render(
        <StructuredWorkspace
          context={context}
          family={family}
          note={original}
          navigate={vi.fn()}
        />,
      );
      expect(
        screen.getByRole("button", { name: "Añadir página" }),
      ).toBeDisabled();
      expect(
        screen.getByRole("button", { name: "Duplicar página" }),
      ).toBeDisabled();
      click("Añadir página");
      click("Duplicar página");
      expect(
        screen.getAllByRole("button", { name: /^Página \d+$/ }),
      ).toHaveLength(30);
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

it("Cornell exposes three independent regions and submits only the intended regional change", async () => {
  const original = note("cornell");
  const page = original.document.pages[0];
  for (const [key, text] of [
    ["cue", "Pregunta original"],
    ["main", "Desarrollo original"],
    ["summary", "Resumen original"],
  ])
    page[key] = {
      heading: key,
      latex: text,
      image_ids: ["shared-" + key],
      private_extension: { keep: key },
    };
  const posted: Record<string, unknown>[] = [];
  vi.stubGlobal(
    "fetch",
    vi.fn(async (_url, options) => {
      const body = JSON.parse(options.body);
      posted.push(body);
      return Response.json({
        ...original,
        document: body.document,
        metadata: { ...original.metadata, ...body.metadata },
        revision: "b".repeat(64),
        latex_body: "Confirmed",
      });
    }),
  );
  render(
    <StructuredWorkspace
      context={context}
      family="cornell"
      note={original}
      navigate={vi.fn()}
    />,
  );
  expect(screen.getAllByLabelText("Región de prueba")).toHaveLength(3);
  const cue = document.querySelector(".cornell-region-cue textarea")!;
  fireEvent.change(cue, { target: { value: "Pregunta modificada" } });
  click("Guardar nota Cornell");
  await screen.findByText("Nota guardada y confirmada en esta biblioteca.");
  const actual = (posted[0].document as typeof original.document).pages[0];
  expect(actual.cue).toMatchObject({
    latex: "Pregunta modificada",
    image_ids: ["shared-cue"],
    private_extension: { keep: "cue" },
  });
  expect(actual.main).toEqual(page.main);
  expect(actual.summary).toEqual(page.summary);
});
