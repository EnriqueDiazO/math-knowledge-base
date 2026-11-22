import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import {
  fireEvent,
  getByLabelText,
  getByRole,
  queryByRole,
  getAllByRole,
} from "@testing-library/dom";
import render from "../src/knowledge-map/component";
import {
  arc,
  compareKeys,
  focus,
  positions,
  project,
  rotate,
  surface,
  unit,
  unrotate,
} from "../src/knowledge-map/geometry";
import {
  acceptResult,
  draftFor,
  freshView,
  intention,
  neighbors,
  visibleEdges,
  visibleNodes,
} from "../src/knowledge-map/model";
import type { Data, Node, Intent } from "../src/knowledge-map/model";
import type { Vec } from "../src/knowledge-map/geometry";
import { persistedView } from "../src/knowledge-map/drafts";

// These tests exercise transport/state and the real document adapter. MathLive's
// keyboard/rendering is exercised by the owned Chrome/Firefox app harness.
vi.mock("../src/knowledge-map/math", () => ({
  makeMath: (latex: string) =>
    Object.assign(document.createElement("math-field"), {
      value: latex,
      setValue(value: string) {
        this.value = value;
      },
    }),
  mathErrors: (latex: string) =>
    latex.trim() && !latex.includes("\\placeholder") ? [] : ["incomplete"],
}));

const node = (key: string, titulo = key): Node => ({
  key,
  id: key.split("@")[0],
  source: "Fuente",
  titulo,
  tipo: "nota",
  contenido_latex: '$G \\times G$ <img onerror="bad()">',
  comentario: "Comentario seguro",
  categorias: ["Álgebra"],
  revision: "rev-" + key,
});
function data(): Data {
  return {
    scope: crypto.randomUUID(),
    nodes: [
      node("a@Fuente", "Álgebra $G$"),
      node("b@Fuente", "Teorema de Bézout"),
    ],
    edges: [
      {
        key: "edge",
        from: "a@Fuente",
        to: "b@Fuente",
        tipo: "implica",
        descripcion: "Real",
      },
    ],
    sources: [{ id: "source", name: "Fuente" }],
    concept_types: ["nota", "teorema"],
    relation_types: ["requiere_concepto", "implica"],
  };
}
let cleanup: (() => void) | undefined;
let parent: HTMLDivElement;
let frames: Map<number, FrameRequestCallback>;
let frameId: number;
let reduced: boolean;
let resizeCallback: ResizeObserverCallback;
let intersectionCallback: IntersectionObserverCallback;
const draw = vi.fn();
let trigger: ReturnType<typeof vi.fn<(key: string, value: Intent) => void>>;
function flush(): void {
  const pending = [...frames.values()];
  frames.clear();
  pending.forEach((cb) => cb(performance.now()));
}
function mount(payload = data()): Data {
  cleanup?.();
  cleanup = render({
    parentElement: parent,
    data: payload,
    setTriggerValue: (key, value) => trigger(key, value as Intent),
  });
  flush();
  return payload;
}
function click(name: string): void {
  fireEvent.click(getByRole(parent, "button", { name }));
  flush();
}
function input(name: string, value: string): void {
  if (name === "Contenido (texto o LaTeX)") {
    click("Fuente LaTeX");
    name = "Fuente LaTeX";
  }
  fireEvent.input(getByLabelText(parent, name), { target: { value } });
}
function choose(name: string, value: string): void {
  fireEvent.change(getByLabelText(parent, name), { target: { value } });
  flush();
}
function submit(): void {
  fireEvent.submit(parent.querySelector("form")!);
}
beforeEach(() => {
  parent = document.createElement("div");
  document.body.append(parent);
  trigger = vi.fn();
  frames = new Map();
  frameId = 0;
  reduced = false;
  vi.stubGlobal("requestAnimationFrame", (callback: FrameRequestCallback) => {
    const id = ++frameId;
    frames.set(id, callback);
    return id;
  });
  vi.stubGlobal("cancelAnimationFrame", (id: number) => frames.delete(id));
  vi.stubGlobal(
    "ResizeObserver",
    class {
      constructor(callback: ResizeObserverCallback) {
        resizeCallback = callback;
      }
      observe() {
        resizeCallback(
          [{ contentRect: { width: 600 } } as ResizeObserverEntry],
          this as unknown as ResizeObserver,
        );
      }
      disconnect() {
        draw("resize-disconnected");
      }
    },
  );
  vi.stubGlobal(
    "IntersectionObserver",
    class {
      constructor(callback: IntersectionObserverCallback) {
        intersectionCallback = callback;
      }
      observe() {
        intersectionCallback(
          [{ isIntersecting: true } as IntersectionObserverEntry],
          this as unknown as IntersectionObserver,
        );
      }
      disconnect() {
        draw("intersection-disconnected");
      }
    },
  );
  vi.stubGlobal(
    "matchMedia",
    () =>
      ({
        get matches() {
          return reduced;
        },
        addEventListener: vi.fn(),
        removeEventListener: vi.fn(),
      }) as unknown as MediaQueryList,
  );
  vi.spyOn(HTMLCanvasElement.prototype, "getContext").mockReturnValue(
    new Proxy(
      {},
      {
        get: (_target, key) =>
          key === "measureText"
            ? (text: string) => ({ width: text.length * 5 })
            : draw,
        set: () => true,
      },
    ) as CanvasRenderingContext2D,
  );
  HTMLCanvasElement.prototype.setPointerCapture = vi.fn();
  HTMLCanvasElement.prototype.releasePointerCapture = vi.fn();
  HTMLDialogElement.prototype.showModal = function () {
    this.open = true;
  };
  HTMLDialogElement.prototype.close = function () {
    this.open = false;
    this.dispatchEvent(new Event("close"));
  };
  Object.defineProperty(window, "mathVirtualKeyboard", {
    configurable: true,
    value: { hide: vi.fn(), container: document.body },
  });
});
afterEach(() => {
  cleanup?.();
  cleanup = undefined;
  parent.remove();
  vi.unstubAllGlobals();
  sessionStorage.clear();
  localStorage.clear();
});

describe("spherical geometry and semantic parity", () => {
  it("normalizes empty vectors and deterministic distributions, preserving existing positions", () => {
    expect(unit([0, 0, 0])).toEqual([0, 0, 1]);
    expect(positions([], {})).toEqual({});
    const first = positions(["b", "a"], {});
    expect(first).toEqual(positions(["a", "b"], {}));
    const next = positions(["a", "b", "c"], first, {
      key: "c",
      point: first.a,
    });
    expect(next.a).toEqual(first.a);
    expect(next.b).toEqual(first.b);
    Object.values(next).forEach((v) => expect(Math.hypot(...v)).toBeCloseTo(1));
    expect(next.c).not.toEqual(first.a);
    expect(positions(["single"], {}).single).toEqual([0, 0, 1]);
    expect(compareKeys("á", "z")).toBe(1);
    expect(compareKeys("a", "b")).toBe(-1);
    expect(compareKeys("a", "a")).toBe(0);
  });
  it.each(
    [[0, 0, 1], [1, 0, 0], [0, 1, 0], unit([-1, 2, -3])].map((v) => [v as Vec]),
  )(
    "focuses rear/polar nodes and reverses camera transforms for %j",
    (vector) => {
      const camera = { yaw: 0.9, pitch: -0.4, zoom: 1.3 };
      unrotate(rotate(vector, camera), camera).forEach((x, i) =>
        expect(x).toBeCloseTo(vector[i]),
      );
      expect(rotate(vector, focus(vector, camera))[2]).toBeCloseTo(1);
      const p = project(vector, focus(vector, camera), 600, 470);
      expect(p.x).toBeCloseTo(300);
      expect(p.y).toBeCloseTo(235);
      expect(Math.hypot(...surface(300, 235, camera, 600, 470))).toBeCloseTo(1);
      expect(project(vector, camera, 600, 470, true).z).toBe(1);
    },
  );
  it.each<[Vec, Vec, boolean]>([
    [[1, 0, 0], [-1, 0, 0], false],
    [[0, 1, 0], [0, 1, 0], true],
    [[1, 0, 0], [1, 0, 0], false],
    [[0, 0, 1], [1, 0, 0], false],
  ])("handles antipodal, coincident and loop arcs %j", (a, b, loop) => {
    const path = arc(a, b, 2, loop);
    path.forEach((v) => {
      expect(Math.hypot(...v)).toBeCloseTo(1);
      v.forEach((x) => expect(Number.isFinite(x)).toBe(true));
    });
    expect(path[0]).toEqual(a);
    expect(path.length).toBeGreaterThan(20);
  });
  it("keeps real identities, direction, filters and neighbors identical between projections", () => {
    const payload = data(),
      view = freshView();
    const nodes = visibleNodes(payload, view),
      edges = visibleEdges(payload, nodes, view);
    view.flat = true;
    expect(visibleEdges(payload, visibleNodes(payload, view), view)).toEqual(
      edges,
    );
    expect(neighbors(payload, "a@Fuente")).toEqual([payload.nodes[1]]);
    view.type = "teorema";
    expect(visibleNodes(payload, view)).toEqual([]);
    expect(visibleEdges(payload, [], view)).toEqual([]);
    view.type = "";
    view.source = "otra";
    expect(visibleNodes(payload, view)).toEqual([]);
    view.source = "";
    view.relation = "equivalente";
    expect(visibleEdges(payload, nodes, view)).toEqual([]);
  });
  it("separates drafts, intentions and confirmed results", () => {
    const payload = data(),
      view = freshView();
    view.selected = payload.nodes[0].key;
    const edit = draftFor(payload, view, "edit", [0, 0, 1]);
    expect(edit.content).toBe(payload.nodes[0].contenido_latex);
    edit.categories = "Álgebra, Grupos, ";
    expect(intention(edit, "id").categorias).toEqual(["Álgebra", "Grupos"]);
    expect(
      intention(
        { ...edit, action: "connect", target: "b@Fuente", reverse: true },
        "id",
      ),
    ).toMatchObject({ key: "a@Fuente", target: "b@Fuente", reverse: true });
    view.pending = intention(edit, "id");
    view.draft = edit;
    acceptResult(
      {
        ...payload,
        result: { operation_id: "other", status: "saved", message: "" },
      },
      view,
    );
    expect(view.pending).toBeDefined();
    acceptResult(
      {
        ...payload,
        result: { operation_id: "id", status: "partial", message: "" },
      },
      view,
    );
    expect(view.pending).toBeDefined();
    acceptResult(
      {
        ...payload,
        result: { operation_id: "id", status: "conflict", message: "" },
      },
      view,
    );
    expect(view.draft).toEqual(edit);
    expect(view.pending).toBeUndefined();
    view.pending = intention(edit, "id2");
    acceptResult(
      {
        ...payload,
        result: {
          operation_id: "id2",
          status: "duplicate",
          message: "",
          key: payload.nodes[1].key,
        },
      },
      view,
    );
    expect(view.draft).toBeUndefined();
    expect(view.selected).toBe(payload.nodes[1].key);
  });
});

describe("editable map interaction", () => {
  it("mounts empty graphs without writes, creates only on submit and retains draft across reruns", () => {
    const payload = data();
    payload.nodes = [];
    payload.edges = [];
    mount(payload);
    expect(trigger).not.toHaveBeenCalled();
    expect(parent.querySelector("canvas")?.dataset.nodes).toBe("0");
    click("Crear concepto aquí");
    input("Nombre", "Teoría <script>");
    input("Contenido (texto o LaTeX)", "$\\alpha$");
    mount(payload);
    expect(getByLabelText(parent, "Nombre")).toHaveValue("Teoría <script>");
    submit();
    const sent = trigger.mock.calls[0][1];
    expect(sent).toMatchObject({
      action: "create",
      titulo: "Teoría <script>",
      contenido_latex: "$\\alpha$",
    });
    expect(parent.querySelector(".editor-dialog")).toBeNull();
    expect(trigger).toHaveBeenCalledTimes(1);
    const next = {
      ...payload,
      nodes: [node("canonical@Fuente", "Teoría <script>")],
      result: {
        operation_id: sent.operation_id,
        status: "saved",
        message: "Confirmado",
        key: "canonical@Fuente",
      },
    };
    mount(next);
    expect(
      getByRole(parent, "heading", { name: "Teoría <script>" }),
    ).toBeVisible();
    expect(parent.querySelector("script")).toBeNull();
    expect(queryByRole(parent, "textbox", { name: "Nombre" })).toBeNull();
  });
  it("cancels without submission and preserves geometry/selection in flat view", () => {
    const payload = mount();
    choose("Seleccionar concepto", payload.nodes[0].key);
    click("Crear conectado");
    click("Conservar borrador y volver");
    expect(trigger).not.toHaveBeenCalled();
    click("Plano");
    expect(parent.querySelector("canvas")?.dataset.edges).toBe("1");
    expect(
      getByRole(parent, "heading", { name: payload.nodes[0].titulo }),
    ).toBeVisible();
    click("Esfera S²");
    click("+ Zoom");
    click("− Zoom");
    click("Ajustar vista");
    click("Abrir nota / edición avanzada");
    expect(trigger.mock.calls[0][0]).toBe("open_note");
    expect(trigger.mock.calls[0][1].key).toBe(payload.nodes[0].key);
  });
  it("connects existing with preview, type and direction; neighbor navigation is real", () => {
    const payload = mount();
    choose("Seleccionar concepto", payload.nodes[0].key);
    click("Conectar con…");
    choose("Destino", payload.nodes[1].key);
    choose("Tipo de relación", "implica");
    fireEvent.click(getByLabelText(parent, "Invertir sentido"));
    expect(parent.textContent).toContain(
      "Teorema de Bézout → [implica] → Álgebra $G$",
    );
    submit();
    expect(trigger.mock.calls[0][1]).toMatchObject({
      action: "connect",
      target: payload.nodes[1].key,
      relation_type: "implica",
      reverse: true,
    });
    mount({
      ...payload,
      result: {
        operation_id: trigger.mock.calls[0][1].operation_id,
        status: "saved",
        message: "Confirmado",
        key: payload.nodes[0].key,
      },
    });
    click("Saliente: Álgebra $G$ → implica → Teorema de Bézout");
    click("Teorema de Bézout");
    expect(
      getByRole(parent, "heading", { name: "Teorema de Bézout" }),
    ).toBeVisible();
  });
  it("creates connected, edits brief fields and renders mathematical/user text safely", () => {
    const payload = mount();
    choose("Seleccionar concepto", payload.nodes[0].key);
    expect(parent.querySelector("img")).toBeNull();
    click("Crear conectado");
    input("Nombre", "Nuevo");
    input("Contenido (texto o LaTeX)", "$x$");
    choose("Tipo de concepto", "teorema");
    choose("Source administrada", "source");
    fireEvent.click(parent.querySelector("summary")!);
    input("Categorías separadas por comas", "A, B");
    input("Comentario", "Comentario");
    submit();
    expect(trigger.mock.calls[0][1]).toMatchObject({
      action: "create_connected",
      key: payload.nodes[0].key,
      tipo: "teorema",
      categorias: ["A", "B"],
    });
    const response = {
      ...payload,
      result: {
        operation_id: trigger.mock.calls[0][1].operation_id,
        status: "saved",
        message: "Guardado",
        key: payload.nodes[0].key,
      },
    };
    mount(response);
    click("Editar ficha");
    click("Fuente LaTeX");
    expect(getByLabelText(parent, "Fuente LaTeX")).toHaveValue(
      payload.nodes[0].contenido_latex,
    );
    click("Fuente LaTeX");
    input("Nombre", "Editado");
    input("Contenido (texto o LaTeX)", "$\\beta$");
    submit();
    expect(trigger.mock.calls.at(-1)![1]).toMatchObject({
      action: "edit",
      revision: payload.nodes[0].revision,
      titulo: "Editado",
    });
  });
  it("retains stale drafts and requires explicit review before adopting current revision", () => {
    const payload = mount();
    choose("Seleccionar concepto", payload.nodes[0].key);
    click("Editar ficha");
    input("Nombre", "Borrador mío");
    submit();
    const sent = trigger.mock.calls[0][1];
    const changed = {
      ...payload,
      nodes: [
        { ...payload.nodes[0], revision: "rev-new", titulo: "Edición ajena" },
        payload.nodes[1],
      ],
      result: {
        operation_id: sent.operation_id,
        status: "conflict",
        message: "Conflicto",
      },
    };
    mount(changed);
    expect(getByLabelText(parent, "Nombre")).toHaveValue("Borrador mío");
    click("Revisar versión actual");
    expect(parent.textContent).toContain("Versión actual de Edición ajena");
    click("He revisado: usar esta versión como base");
    submit();
    expect(trigger.mock.calls.at(-1)![1]).toMatchObject({
      titulo: "Borrador mío",
      revision: "rev-new",
    });
    expect(trigger.mock.calls.at(-1)![1].operation_id).not.toBe(
      sent.operation_id,
    );
  });
  it("reconciles an uncertain/partial result with the same operation ID", () => {
    const payload = mount();
    click("Crear concepto aquí");
    input("Nombre", "Guardado parcial");
    input("Contenido (texto o LaTeX)", "$G$");
    submit();
    const original = trigger.mock.calls[0][1];
    mount({
      ...payload,
      result: {
        operation_id: original.operation_id,
        status: "partial",
        message: "Concepto guardado; falta vínculo",
      },
    });
    click("Reconciliar el mismo intento");
    expect(trigger.mock.calls.at(-1)![1]).toEqual(original);
    click("Recuperar borradores");
    click("Guardado parcial · create");
    expect(getByLabelText(parent, "Nombre")).toHaveValue("Guardado parcial");
  });
  it("shows filtered saved concepts only after an explicit filter action", () => {
    const payload = mount();
    choose("Tipo visible", "nota");
    click("Crear concepto aquí");
    input("Nombre", "Teorema nuevo");
    input("Contenido (texto o LaTeX)", "$T$");
    choose("Tipo de concepto", "teorema");
    submit();
    const newNode = { ...node("t@Fuente", "Teorema nuevo"), tipo: "teorema" };
    mount({
      ...payload,
      nodes: [...payload.nodes, newNode],
      result: {
        operation_id: trigger.mock.calls[0][1].operation_id,
        status: "saved",
        message: "Guardado",
        key: newNode.key,
      },
    });
    expect(parent.querySelector("canvas")?.dataset.nodes).toBe("2");
    click("Mostrar concepto guardado");
    expect(parent.querySelector("canvas")?.dataset.nodes).toBe("3");
    choose("Fuente visible", "Fuente");
    choose("Relación visible", "requiere_concepto");
    expect(parent.querySelector("canvas")?.dataset.edges).toBe("0");
  });
  it("searches locally, protects drafts from selection changes and supports keyboard/touch rotation", () => {
    const payload = mount();
    input("Buscar nombre o ID", "bézout");
    expect(
      getAllByRole(parent, "option").some(
        (o) => o.textContent === "Álgebra $G$ · Fuente",
      ),
    ).toBe(false);
    choose("Seleccionar concepto", payload.nodes[1].key);
    const canvas = parent.querySelector("canvas")!;
    fireEvent.keyDown(canvas, { key: "ArrowLeft" });
    fireEvent.keyDown(canvas, { key: "Tab" });
    flush();
    fireEvent.pointerDown(canvas, { pointerId: 1, clientX: 10, clientY: 10 });
    fireEvent.pointerMove(canvas, { pointerId: 1, clientX: 40, clientY: 20 });
    fireEvent.pointerUp(canvas, { pointerId: 1, clientX: 40, clientY: 20 });
    flush();
    fireEvent.pointerDown(canvas, { pointerId: 2 });
    fireEvent.pointerCancel(canvas, { pointerId: 2 });
    fireEvent.pointerLeave(canvas);
    flush();
    click("Editar ficha");
    choose("Seleccionar concepto", payload.nodes[1].key);
    expect(getByLabelText(parent, "Nombre")).toHaveValue(
      payload.nodes[1].titulo,
    );
    fireEvent.contextMenu(canvas, { clientX: 300, clientY: 235 });
    expect(trigger).not.toHaveBeenCalled();
  });
  it("pauses animation offscreen/hidden/reduced motion and cleans every scheduled frame", () => {
    mount();
    click("Giro suave");
    expect(frames.size).toBe(1);
    flush();
    expect(frames.size).toBe(1);
    intersectionCallback(
      [{ isIntersecting: false } as IntersectionObserverEntry],
      {} as IntersectionObserver,
    );
    flush();
    expect(frames.size).toBe(0);
    intersectionCallback(
      [{ isIntersecting: true } as IntersectionObserverEntry],
      {} as IntersectionObserver,
    );
    flush();
    reduced = true;
    flush();
    expect(frames.size).toBe(0);
    click("Pausar giro");
    click("Giro suave");
    flush();
    expect(frames.size).toBe(0);
    cleanup?.();
    expect(frames.size).toBe(0);
    expect(draw).toHaveBeenCalledWith("resize-disconnected");
    expect(draw).toHaveBeenCalledWith("intersection-disconnected");
  });
  it("handles storage disabled and unavailable sources without losing an in-memory draft", () => {
    vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => {
      throw new Error("disabled");
    });
    const payload = data();
    payload.sources = [];
    mount(payload);
    click("Crear concepto aquí");
    input("Nombre", "Retenido");
    expect(
      getByRole(parent, "button", { name: "Guardar concepto" }),
    ).toBeDisabled();
    mount(payload);
    expect(getByLabelText(parent, "Nombre")).toHaveValue("Retenido");
    expect(trigger).not.toHaveBeenCalled();
  });
});

it("recovers a conflicting partial edit by explicit review, without pretending cancellation reverted data", () => {
  const payload = mount();
  choose("Seleccionar concepto", payload.nodes[0].key);
  click("Editar ficha");
  input("Nombre", "Mi título");
  submit();
  const sent = trigger.mock.calls[0][1];
  mount({
    ...payload,
    nodes: [
      {
        ...payload.nodes[0],
        titulo: "Mi título",
        contenido_latex: "Cambio externo",
        revision: "review-partial",
      },
      payload.nodes[1],
    ],
    result: {
      operation_id: sent.operation_id,
      status: "partial",
      message: "Ficha guardada, contenido en conflicto",
    },
  });
  click("Revisar edición parcial con mi borrador");
  expect(getByLabelText(parent, "Nombre")).toHaveValue("Mi título");
  click("Revisar versión actual");
  expect(parent.textContent).toContain("Cambio externo");
  click("He revisado: usar esta versión como base");
  click("Conservar borrador y volver");
  expect(parent.textContent).toContain("no se publicó contenido nuevo");
  expect(trigger).toHaveBeenCalledTimes(1);
});

describe("study presentation and recoverable goals", () => {
  it("keeps a goal as a draft until confirmed and requires an explicit self-review", () => {
    const payload = mount();
    input("Pregunta o concepto pendiente", "¿Por qué?");
    click("Reservar pendiente aquí");
    expect(trigger).not.toHaveBeenCalled();
    expect(persistedView(payload.scope)?.goals).toHaveLength(1);
    click("Pendiente: ¿Por qué?");
    expect(getByLabelText(parent, "Nombre")).toHaveValue("¿Por qué?");
    input("Contenido (texto o LaTeX)", "Explicación con $x$.");
    click("Conservar borrador y volver");
    click("En elaboración: ¿Por qué?");
    expect(getByLabelText(parent, "Fuente LaTeX")).toHaveValue(
      "Explicación con $x$.",
    );
    submit();
    const operation = trigger.mock.calls[0][1],
      confirmed = node("goal@Fuente", "¿Por qué?");
    mount({
      ...payload,
      nodes: [...payload.nodes, confirmed],
      result: {
        operation_id: operation.operation_id,
        status: "saved",
        message: "Guardado",
        key: confirmed.key,
      },
    });
    const goal = persistedView(payload.scope)?.goals?.[0];
    expect(goal?.conceptKey).toBe(confirmed.key);
    expect(goal?.state).toBe("working");
    expect(persistedView(payload.scope)?.points[confirmed.key]).toEqual(
      goal?.point,
    );
    click("Marcar Revisado por mí");
    expect(parent.textContent).toContain("1 de 1 objetivos marcados por ti");
    click("Volver a En elaboración");
    expect(persistedView(payload.scope)?.goals?.[0].state).toBe("working");
  });
  it("changes thematic presentation without reclassifying or writing concepts", () => {
    const payload = data();
    payload.nodes[0].categorias = ["Álgebra", "Geometría"];
    payload.nodes[1].categorias = ["Geometría"];
    const original = structuredClone(payload);
    mount(payload);
    fireEvent.click(getByLabelText(parent, "Álgebra"));
    fireEvent.click(getByLabelText(parent, "Geometría"));
    click("Activar estilo mandala");
    click("Organizar por áreas");
    flush();
    expect(persistedView(payload.scope)?.areas).toEqual([
      "Álgebra",
      "Geometría",
    ]);
    expect(persistedView(payload.scope)?.mandala).toBe(true);
    click("Disposición orgánica: ensayo breve");
    click("Desactivar estilo mandala");
    expect(payload).toEqual(original);
    expect(trigger).not.toHaveBeenCalled();
    expect(parent.querySelector("canvas")?.dataset.nodes).toBe("2");
  });
  it("persists a view only on request and adopts the acknowledged revision", () => {
    const payload = mount();
    input("Nombre de la vista", "Vista de prueba");
    click("Guardar disposición");
    const request = trigger.mock.calls[0][1];
    expect(request.action).toBe("save_view");
    expect(request.view_state?.version).toBe(1);
    mount({
      ...payload,
      result: {
        operation_id: request.operation_id,
        status: "saved",
        message: "Disposición guardada",
        view_revision: "confirmed",
        map_uid: request.map_uid,
      },
    });
    expect(persistedView(payload.scope)?.viewRevision).toBe("confirmed");
    expect(persistedView(payload.scope)?.layoutDirty).toBe(false);
    click("Guardar disposición");
    expect(trigger.mock.calls[1][1].revision).toBe("confirmed");
  });
  it("loads another saved view without aliasing its positions or losing unrelated positions to filters", () => {
    const payload = data(),
      state = {
        version: 1 as const,
        points: {
          [payload.nodes[0].key]: [0, 0, 1] as Vec,
          [payload.nodes[1].key]: [1, 0, 0] as Vec,
        },
        flatPoints: {},
        pinned: [],
        areas: [],
        mandala: false,
        goals: [],
      };
    payload.views = [
      { uid: "other-view", name: "Otra esfera", revision: "r", state },
    ];
    mount(payload);
    choose("Abrir vista guardada", "other-view");
    choose("Seleccionar concepto", payload.nodes[0].key);
    choose("Tipo visible", "teorema");
    expect(persistedView(payload.scope)?.points[payload.nodes[1].key]).toEqual([
      1, 0, 0,
    ]);
    expect(payload.views[0].state).toEqual(state);
  });
  it("reopens a complete reader and changes its size without changing camera or stored content", () => {
    const payload = mount();
    choose("Seleccionar concepto", payload.nodes[0].key);
    const before = persistedView(payload.scope)?.camera;
    click("Leer concepto");
    expect(parent.querySelector(".reader-dialog")).not.toBeNull();
    input("Tamaño de lectura", "22");
    click("Cerrar lectura");
    expect(persistedView(payload.scope)?.camera).toEqual(before);
    expect(parent.querySelector(".reader-dialog")).toBeNull();
  });
  it("discards only the selected draft after a second explicit decision", () => {
    const payload = mount();
    click("Crear concepto aquí");
    input("Nombre", "Primero");
    click("Conservar borrador y volver");
    click("Crear concepto aquí");
    input("Nombre", "Segundo");
    click("Descartar borrador…");
    click("Seguir escribiendo");
    expect(getByLabelText(parent, "Nombre")).toHaveValue("Segundo");
    click("Descartar borrador…");
    click("Sí, descartar este borrador");
    click("Recuperar borradores");
    expect(parent.textContent).toContain("Primero · create");
    expect(parent.textContent).not.toContain("Segundo · create");
    expect(trigger).not.toHaveBeenCalled();
    expect(persistedView(payload.scope)?.pending).toBeUndefined();
    click("Cerrar borradores");
  });
  it("uses actual resize dimensions when expanded and restores the normal host on exit", () => {
    const payload = mount();
    choose("Seleccionar concepto", payload.nodes[0].key);
    const before = persistedView(payload.scope)?.camera;
    click("Expandir mapa");
    const canvas = parent.querySelector("canvas")!;
    expect(canvas.closest("dialog")?.open).toBe(true);
    resizeCallback(
      [{ contentRect: { width: 1000, height: 820 } } as ResizeObserverEntry],
      {} as ResizeObserver,
    );
    flush();
    expect(canvas.width).toBe(1000);
    expect(canvas.height).toBe(820);
    expect(canvas.dataset.cssHeight).toBe("820");
    click("Volver a vista normal");
    expect(canvas.closest("dialog")).toBeNull();
    expect(persistedView(payload.scope)?.camera).toEqual(before);
  });
  it("supports accessible relocation, pinning and undo without semantic writes", () => {
    const payload = mount();
    choose("Seleccionar concepto", payload.nodes[0].key);
    const before = persistedView(payload.scope)!.points[payload.nodes[0].key];
    click("Mover nodo a la derecha");
    const after = persistedView(payload.scope)!.points[payload.nodes[0].key];
    expect(after).not.toEqual(before);
    expect(Math.hypot(...after)).toBeCloseTo(1);
    click("Deshacer reubicación");
    expect(persistedView(payload.scope)!.points[payload.nodes[0].key]).toEqual(
      before,
    );
    click("Fijar posición");
    click("Mover nodo arriba");
    expect(persistedView(payload.scope)!.points[payload.nodes[0].key]).toEqual(
      before,
    );
    click("Desfijar posición");
    click("Restablecer disposición");
    expect(trigger).not.toHaveBeenCalled();
  });
});
