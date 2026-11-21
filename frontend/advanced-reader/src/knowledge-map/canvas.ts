import {
  arc,
  compareKeys,
  focus,
  project,
  rotate,
  unit,
  unrotate,
} from "./geometry";
import type { Vec, Point } from "./geometry";
import { visibleEdges, visibleNodes, neighbors } from "./model";
import type { Data, View, Node, Edge } from "./model";
import { dragSurface } from "./layout";
import { studyTheme as theme } from "./theme";
import { areaColor, regions } from "./areas";
export const colors: Record<string, string> = {
  definicion: theme.turquoise,
  teorema: theme.sky,
  proposicion: theme.amber,
  corolario: theme.sky,
  lema: theme.turquoise,
  ejemplo: theme.amber,
  nota: theme.muted,
};
type Path = { edge: Edge; lane: number; points: Vec[] };
type Drag = {
  startX: number;
  startY: number;
  x: number;
  y: number;
  moved: boolean;
  key: string;
  side: number;
  point?: Vec;
  flat?: [number, number];
};
export class MapCanvas {
  private context: CanvasRenderingContext2D;
  private width = 600;
  private height = 540;
  private frame = 0;
  private lastTime = 0;
  private shown = true;
  private stopped = false;
  private hover = "";
  private hoverEdge = "";
  private drag?: Drag;
  private nodes: Node[] = [];
  private paths: Path[] = [];
  private projected = new Map<string, Point>();
  private projectedEdges = new Map<string, Point[]>();
  private boxes: { x: number; y: number; width: number }[] = [];
  private controller = new AbortController();
  private resize: ResizeObserver;
  private intersection: IntersectionObserver;
  private motion = window.matchMedia("(prefers-reduced-motion: reduce)");
  private history: {
    points: Record<string, Vec>;
    flat: Record<string, [number, number]>;
    goals: Vec[];
  }[] = [];
  private priority = new Set<string>();
  private focusedEndpoints = new Set<string>();
  private areaShapes: ReturnType<typeof regions> = [];
  constructor(
    private canvas: HTMLCanvasElement,
    private data: Data,
    private view: View,
    private select: (key: string) => void,
    private create: (point: Vec) => void,
    private changed: () => void,
    private edgeSelected?: (key: string) => void,
  ) {
    const context = canvas.getContext("2d");
    if (!context)
      throw new Error("Canvas no disponible; usa los formularios accesibles.");
    this.context = context;
    const options = { signal: this.controller.signal };
    canvas.addEventListener(
      "pointerdown",
      (event) => this.down(event),
      options,
    );
    canvas.addEventListener(
      "pointermove",
      (event) => this.move(event),
      options,
    );
    canvas.addEventListener("pointerup", (event) => this.up(event), options);
    canvas.addEventListener("pointercancel", () => this.cancel(), options);
    canvas.addEventListener(
      "pointerleave",
      () => {
        this.hover = "";
        this.hoverEdge = "";
        this.request();
      },
      options,
    );
    canvas.addEventListener(
      "contextmenu",
      (event) => {
        event.preventDefault();
        this.pause();
        const rect = canvas.getBoundingClientRect();
        this.create(
          dragSurface(
            event.clientX - rect.left,
            event.clientY - rect.top,
            view.camera,
            this.width,
            this.height,
            1,
          ),
        );
      },
      options,
    );
    canvas.addEventListener(
      "keydown",
      (event) => this.keyboard(event),
      options,
    );
    document.addEventListener(
      "visibilitychange",
      () => this.request(),
      options,
    );
    this.motion.addEventListener(
      "change",
      () => {
        this.pause();
        this.request();
      },
      options,
    );
    this.resize = new ResizeObserver((entries) => {
      this.width = Math.max(200, entries[0].contentRect.width);
      this.height = Math.max(
        200,
        entries[0].contentRect.height ||
          canvas.getBoundingClientRect().height ||
          540,
      );
      const dpr = Math.min(window.devicePixelRatio || 1, 2);
      canvas.width = Math.round(this.width * dpr);
      canvas.height = Math.round(this.height * dpr);
      this.context.setTransform(dpr, 0, 0, dpr, 0, 0);
      canvas.dataset.cssWidth = String(this.width);
      canvas.dataset.cssHeight = String(this.height);
      this.request();
    });
    this.resize.observe(canvas);
    this.intersection = new IntersectionObserver((entries) => {
      this.shown = entries[0].isIntersecting;
      this.request();
    });
    this.intersection.observe(canvas);
    this.update(data);
  }
  update(data: Data): void {
    this.data = data;
    this.nodes = visibleNodes(data, this.view);
    const lanes = new Map<string, number>();
    this.paths = visibleEdges(data, this.nodes, this.view).map((edge) => {
      const pair = [edge.from, edge.to].sort(compareKeys).join("\u0000"),
        lane = lanes.get(pair) ?? 0;
      lanes.set(pair, lane + 1);
      return {
        edge,
        lane,
        points: arc(
          this.view.points[edge.from],
          this.view.points[edge.to],
          lane,
          edge.from === edge.to,
        ),
      };
    });
    this.areaShapes = regions(data, this.view);
    this.canvas.dataset.nodes = String(this.nodes.length);
    this.canvas.dataset.edges = String(this.paths.length);
    this.canvas.dataset.focusedEdge = this.view.focusedEdge ?? "";
    this.request();
  }
  pause(): void {
    this.view.auto = false;
  }
  request(): void {
    if (!this.frame && !this.stopped)
      this.frame = requestAnimationFrame((time) => this.draw(time));
  }
  rememberLayout(): void {
    this.history.push({
      points: structuredClone(this.view.points),
      flat: structuredClone(this.view.flatPoints ?? {}),
      goals: (this.view.goals ?? []).map((g) => [...g.point] as Vec),
    });
    if (this.history.length > 30) this.history.shift();
  }
  undoLayout(): void {
    const previous = this.history.pop();
    if (!previous) return;
    this.view.points = previous.points;
    this.view.flatPoints = previous.flat;
    (this.view.goals ?? []).forEach((g, i) => {
      if (previous.goals[i]) g.point = previous.goals[i];
    });
    this.view.layoutDirty = true;
    this.update(this.data);
    this.changed();
  }
  relocateSelected(x: number, y: number): void {
    const key = this.view.selected,
      point = this.view.points[key];
    if (!point || this.view.pinned?.includes(key)) return;
    this.rememberLayout();
    const p = rotate(point, this.view.camera);
    this.view.points[key] = unit(
      unrotate(unit([p[0] + x, p[1] + y, p[2]]), this.view.camera),
    );
    this.view.layoutDirty = true;
    this.update(this.data);
    this.changed();
  }
  private down(event: PointerEvent): void {
    this.pause();
    const rect = this.canvas.getBoundingClientRect(),
      key = this.hit(event.clientX - rect.left, event.clientY - rect.top);
    const point = key.startsWith("goal:")
      ? this.view.goals?.find((g) => "goal:" + g.id === key)?.point
      : this.view.points[key];
    this.drag = {
      startX: event.clientX,
      startY: event.clientY,
      x: event.clientX,
      y: event.clientY,
      moved: false,
      key,
      side: point && rotate(point, this.view.camera)[2] < 0 ? -1 : 1,
      point: point ? ([...point] as Vec) : undefined,
      flat: this.view.flatPoints?.[key],
    };
    this.canvas.setPointerCapture(event.pointerId);
  }
  private move(event: PointerEvent): void {
    const rect = this.canvas.getBoundingClientRect(),
      x = event.clientX - rect.left,
      y = event.clientY - rect.top;
    if (!this.drag) {
      this.hover = this.hit(x, y);
      this.hoverEdge = this.hover ? "" : this.hitEdge(x, y);
      const node = this.data.nodes.find((n) => n.key === this.hover),
        edge = this.data.edges.find((e) => e.key === this.hoverEdge);
      this.canvas.title =
        node?.titulo ??
        (edge
          ? `${this.title(edge.from)} → ${edge.tipo.replaceAll("_", " ")} → ${this.title(edge.to)}`
          : "");
      this.request();
      return;
    }
    const drag = this.drag;
    if (
      !drag.moved &&
      Math.hypot(event.clientX - drag.startX, event.clientY - drag.startY) < 5
    )
      return;
    if (!drag.moved && drag.key) this.rememberLayout();
    drag.moved = true;
    if (drag.key && !this.view.pinned?.includes(drag.key)) {
      if (drag.key.startsWith("goal:")) {
        const goal = this.view.goals?.find((g) => "goal:" + g.id === drag.key);
        if (goal)
          goal.point = dragSurface(
            x,
            y,
            this.view.camera,
            this.width,
            this.height,
            drag.side,
          );
      } else if (this.view.flat) {
        this.view.flatPoints ??= {};
        const radius =
          Math.min(this.width, this.height) * 0.36 * this.view.camera.zoom;
        this.view.flatPoints[drag.key] = [
          (x - this.width / 2) / radius,
          (this.height / 2 - y) / radius,
        ];
      } else
        this.view.points[drag.key] = dragSurface(
          x,
          y,
          this.view.camera,
          this.width,
          this.height,
          drag.side,
        );
      this.view.layoutDirty = true;
      this.refreshIncident(drag.key);
    } else if (!drag.key) {
      this.view.camera.yaw += (event.clientX - drag.x) * 0.007;
      this.view.camera.pitch += (event.clientY - drag.y) * 0.007;
    }
    drag.x = event.clientX;
    drag.y = event.clientY;
    this.changed();
    this.request();
  }
  private up(event: PointerEvent): void {
    const drag = this.drag;
    this.drag = undefined;
    try {
      this.canvas.releasePointerCapture(event.pointerId);
    } catch {
      /* Pointer capture may already have been cancelled by the browser. */
    }
    if (!drag?.moved) {
      const rect = this.canvas.getBoundingClientRect(),
        key = this.hit(event.clientX - rect.left, event.clientY - rect.top);
      if (key) this.select(key);
      else {
        const edge = this.hitEdge(
          event.clientX - rect.left,
          event.clientY - rect.top,
        );
        if (edge) this.edgeSelected?.(edge);
      }
    }
    this.changed();
    this.request();
  }
  private cancel(): void {
    if (this.drag?.moved && this.drag.key) this.undoLayout();
    this.drag = undefined;
    this.request();
  }
  private refreshIncident(key: string): void {
    this.paths.forEach((path) => {
      if (path.edge.from === key || path.edge.to === key)
        path.points = arc(
          this.view.points[path.edge.from],
          this.view.points[path.edge.to],
          path.lane,
          path.edge.from === path.edge.to,
        );
    });
    this.areaShapes = regions(this.data, this.view);
  }
  private hit(x: number, y: number): string {
    let key = "",
      depth = -2;
    this.projected.forEach((point, id) => {
      if (
        (!this.view.frontOnly || point.z >= 0) &&
        Math.hypot(point.x - x, point.y - y) < 16 &&
        point.z > depth
      ) {
        key = id;
        depth = point.z;
      }
    });
    return key;
  }
  private hitEdge(x: number, y: number): string {
    let found = "",
      best = 7;
    this.projectedEdges.forEach((points, key) => {
      for (let i = 1; i < points.length; i++) {
        const a = points[i - 1],
          b = points[i];
        if (this.view.frontOnly && b.z < 0) continue;
        const dx = b.x - a.x,
          dy = b.y - a.y,
          t = Math.max(
            0,
            Math.min(
              1,
              ((x - a.x) * dx + (y - a.y) * dy) / (dx * dx + dy * dy || 1),
            ),
          ),
          distance = Math.hypot(x - a.x - t * dx, y - a.y - t * dy);
        if (distance < best) {
          best = distance;
          found = key;
        }
      }
    });
    return found;
  }
  private keyboard(event: KeyboardEvent): void {
    const delta: Record<string, [number, number]> = {
      ArrowLeft: [-0.12, 0],
      ArrowRight: [0.12, 0],
      ArrowUp: [0, -0.12],
      ArrowDown: [0, 0.12],
    };
    if (!delta[event.key]) return;
    event.preventDefault();
    this.pause();
    this.view.camera.yaw += delta[event.key][0];
    this.view.camera.pitch += delta[event.key][1];
    this.changed();
    this.request();
  }
  bringFront(key: string): void {
    const point = this.view.points[key];
    if (!point) return;
    this.pause();
    this.view.camera = focus(point, this.view.camera);
    this.request();
  }
  private title(key: string): string {
    return this.data.nodes.find((n) => n.key === key)?.titulo ?? key;
  }
  private point(v: Vec, key?: string): Point {
    const p = project(
      v,
      this.view.camera,
      this.width,
      this.height,
      this.view.flat,
    );
    const flat = key && this.view.flatPoints?.[key];
    if (this.view.flat && flat) {
      const r =
        Math.min(this.width, this.height) * 0.36 * this.view.camera.zoom;
      return {
        x: this.width / 2 + flat[0] * r,
        y: this.height / 2 - flat[1] * r,
        z: 1,
      };
    }
    return p;
  }
  private draw(time: number): void {
    this.frame = 0;
    if (this.stopped || document.hidden || !this.shown) {
      this.lastTime = 0;
      return;
    }
    const start = performance.now(),
      ctx = this.context;
    const animate =
      this.view.auto &&
      !this.view.draft &&
      !this.view.reader &&
      !this.view.selected &&
      !this.motion.matches &&
      !this.view.flat;
    if (animate && this.lastTime)
      this.view.camera.yaw += Math.min(time - this.lastTime, 50) * 0.000045;
    this.lastTime = time;
    this.priority = new Set(
      neighbors(this.data, this.view.selected).map((n) => n.key),
    );
    const selectedEdge = this.data.edges.find(
      (e) => e.key === this.view.focusedEdge,
    );
    this.focusedEndpoints = new Set(
      selectedEdge ? [selectedEdge.from, selectedEdge.to] : [],
    );
    ctx.clearRect(0, 0, this.width, this.height);
    const radius =
      Math.min(this.width, this.height) * 0.36 * this.view.camera.zoom;
    ctx.strokeStyle = theme.line;
    ctx.lineWidth = 1;
    if (!this.view.flat) {
      ctx.beginPath();
      ctx.arc(this.width / 2, this.height / 2, radius, 0, Math.PI * 2);
      ctx.stroke();
      this.drawAreas(ctx);
    }
    this.drawEdges(ctx);
    this.projected.clear();
    this.boxes = [];
    const projected = this.nodes
      .map((node) => ({
        node,
        point: this.point(this.view.points[node.key], node.key),
      }))
      .filter((p) => !this.view.frontOnly || p.point.z >= 0)
      .sort((a, b) => a.point.z - b.point.z);
    const chosen = projected.find((p) => p.node.key === this.view.selected);
    if (chosen)
      this.boxes.push(this.labelBox(ctx, chosen.node.titulo, chosen.point));
    projected.forEach(({ node, point }) => this.drawNode(ctx, node, point));
    this.drawGoals(ctx);
    this.drawProposal(ctx);
    ctx.globalAlpha = 1;
    this.canvas.dataset.renderMs = String(performance.now() - start);
    if (animate) this.request();
  }
  private drawAreas(ctx: CanvasRenderingContext2D): void {
    this.areaShapes.forEach((area) => {
      const center = this.point(area.center);
      if (this.view.frontOnly && center.z < 0) return;
      ctx.fillStyle = area.color;
      ctx.strokeStyle = area.color;
      ctx.globalAlpha = center.z < 0 ? 0.025 : 0.1;
      ctx.beginPath();
      area.outline.forEach((v, i) => {
        const p = this.point(v);
        if (!i) ctx.moveTo(p.x, p.y);
        else ctx.lineTo(p.x, p.y);
      });
      ctx.closePath();
      ctx.fill();
      ctx.globalAlpha = center.z < 0 ? 0.04 : 0.24;
      ctx.lineWidth = 1;
      ctx.setLineDash([2, 5]);
      area.petals.forEach((petal) => {
        ctx.beginPath();
        petal.forEach((v, i) => {
          const p = this.point(v);
          if (!i) ctx.moveTo(p.x, p.y);
          else ctx.lineTo(p.x, p.y);
        });
        ctx.stroke();
      });
      ctx.setLineDash([]);
      if (center.z > 0.05) {
        ctx.font = "14px system-ui";
        ctx.fillStyle = area.color;
        ctx.globalAlpha = 0.7;
        ctx.fillText(area.name, center.x, center.y + 32);
      }
    });
  }
  private drawEdges(ctx: CanvasRenderingContext2D): void {
    const selectedEdge = this.view.focusedEdge ?? this.hoverEdge;
    this.projectedEdges.clear();
    const paths = this.paths.map((path) => {
      const from = this.point(this.view.points[path.edge.from], path.edge.from),
        to = this.point(this.view.points[path.edge.to], path.edge.to);
      const points = this.view.flat
        ? Array.from({ length: 25 }, (_, i) => ({
            x: from.x + ((to.x - from.x) * i) / 24,
            y:
              from.y +
              ((to.y - from.y) * i) / 24 +
              Math.sin((i / 24) * Math.PI) * path.lane * 12,
            z: 1,
          }))
        : path.points.map((p) => this.point(p));
      this.projectedEdges.set(path.edge.key, points);
      return {
        points,
        strong: selectedEdge
          ? path.edge.key === selectedEdge
          : [this.hover, this.view.selected].some(
              (key) =>
                !!key && (path.edge.from === key || path.edge.to === key),
            ),
      };
    });
    for (const strong of [false, true])
      for (const back of [true, false]) {
        ctx.lineWidth = strong ? 2.4 : 0.8;
        ctx.strokeStyle = strong ? theme.amber : theme.sky;
        ctx.globalAlpha = strong ? 1 : back ? 0.18 : selectedEdge ? 0.2 : 0.72;
        ctx.beginPath();
        paths
          .filter((p) => p.strong === strong)
          .forEach((path) => {
            for (let i = 1; i < path.points.length; i++) {
              const a = path.points[i - 1],
                b = path.points[i];
              if (
                b.z < 0 !== back ||
                (this.view.flat && Math.abs(a.x - b.x) > this.width * 0.4)
              )
                continue;
              ctx.moveTo(a.x, a.y);
              ctx.lineTo(b.x, b.y);
            }
            const tip = path.points.at(-3)!,
              previous = path.points.at(-4)!;
            if (tip.z < 0 === back) {
              const angle = Math.atan2(tip.y - previous.y, tip.x - previous.x);
              ctx.moveTo(
                tip.x - 8 * Math.cos(angle - 0.5),
                tip.y - 8 * Math.sin(angle - 0.5),
              );
              ctx.lineTo(tip.x, tip.y);
              ctx.lineTo(
                tip.x - 8 * Math.cos(angle + 0.5),
                tip.y - 8 * Math.sin(angle + 0.5),
              );
            }
          });
        ctx.stroke();
      }
  }
  private labelBox(
    ctx: CanvasRenderingContext2D,
    text: string,
    p: Point,
  ): { x: number; y: number; width: number } {
    ctx.font = "15px system-ui";
    const width = Math.min(ctx.measureText(text).width, this.width - 12);
    return {
      x: Math.max(6, Math.min(p.x + 14, this.width - width - 6)),
      y: p.y - 13,
      width,
    };
  }
  private drawNode(ctx: CanvasRenderingContext2D, node: Node, p: Point): void {
    this.projected.set(node.key, p);
    const endpoint = this.focusedEndpoints.has(node.key),
      selected = node.key === this.view.selected,
      active = selected || node.key === this.hover || endpoint;
    ctx.globalAlpha =
      p.z < 0 ? 0.22 : this.view.focusedEdge && !active ? 0.2 : 0.8 + 0.2 * p.z;
    ctx.fillStyle = colors[node.tipo] ?? "#bfccd9";
    ctx.beginPath();
    const radius = active ? 7 : 5;
    if (node.tipo === "teorema") {
      ctx.moveTo(p.x, p.y - radius);
      ctx.lineTo(p.x + radius, p.y + radius);
      ctx.lineTo(p.x - radius, p.y + radius);
      ctx.closePath();
    } else if (node.tipo === "definicion")
      ctx.rect(p.x - radius, p.y - radius, radius * 2, radius * 2);
    else ctx.arc(p.x, p.y, radius, 0, Math.PI * 2);
    ctx.fill();
    if (selected || endpoint) {
      ctx.strokeStyle = endpoint ? theme.amber : theme["selected-border"];
      ctx.lineWidth = 2;
      ctx.beginPath();
      ctx.arc(p.x, p.y, 11, 0, Math.PI * 2);
      ctx.stroke();
    }
    const memberships = (this.view.areas ?? []).filter((a) =>
      node.categorias.includes(a),
    );
    if (memberships.length > 1)
      memberships.forEach((area, i) => {
        ctx.strokeStyle = areaColor(area);
        ctx.lineWidth = 2;
        ctx.beginPath();
        ctx.arc(
          p.x,
          p.y,
          14,
          (i / memberships.length) * Math.PI * 2,
          ((i + 0.8) / memberships.length) * Math.PI * 2,
        );
        ctx.stroke();
      });
    if (
      active ||
      this.priority.has(node.key) ||
      (this.nodes.length < 25 && p.z > 0.15)
    ) {
      const box = this.labelBox(ctx, node.titulo, p);
      if (
        !active &&
        this.boxes.some(
          (other) =>
            Math.abs(other.y - box.y) < 19 &&
            box.x < other.x + other.width + 5 &&
            box.x + box.width + 5 > other.x,
        )
      )
        return;
      this.boxes.push(box);
      ctx.font = active ? "bold 16px system-ui" : "14px system-ui";
      ctx.globalAlpha = 1;
      ctx.fillStyle = theme.bg;
      ctx.fillRect(box.x - 4, box.y - 18, box.width + 8, 23);
      ctx.fillStyle = theme.text;
      ctx.fillText(node.titulo, box.x, box.y, box.width);
    }
  }
  private drawGoals(ctx: CanvasRenderingContext2D): void {
    (this.view.goals ?? [])
      .filter((g) => !g.conceptKey)
      .forEach((goal) => {
        const p = this.point(goal.point);
        if (this.view.frontOnly && p.z < 0) return;
        this.projected.set("goal:" + goal.id, p);
        ctx.globalAlpha = p.z < 0 ? 0.2 : 0.9;
        ctx.strokeStyle = theme.amber;
        ctx.lineWidth = 2;
        ctx.setLineDash([3, 3]);
        ctx.beginPath();
        ctx.moveTo(p.x, p.y - 10);
        ctx.lineTo(p.x + 10, p.y);
        ctx.lineTo(p.x, p.y + 10);
        ctx.lineTo(p.x - 10, p.y);
        ctx.closePath();
        ctx.stroke();
        ctx.setLineDash([]);
        ctx.font = "14px system-ui";
        ctx.fillStyle = theme.text;
        ctx.fillText(
          `${goal.state === "pending" ? "Pendiente" : "En elaboración"}: ${goal.label}`,
          p.x + 15,
          p.y,
          this.width - p.x - 20,
        );
      });
  }
  private drawProposal(ctx: CanvasRenderingContext2D): void {
    const draft = this.view.draft;
    if (!draft) return;
    if (draft.action.startsWith("create")) {
      const p = this.point(draft.point);
      ctx.strokeStyle = "#ffffff";
      ctx.globalAlpha = 0.9;
      ctx.setLineDash([4, 4]);
      ctx.beginPath();
      ctx.arc(p.x, p.y, 12, 0, Math.PI * 2);
      ctx.stroke();
      ctx.setLineDash([]);
    }
    if (!["connect", "create_connected"].includes(draft.action)) return;
    const origin = this.view.points[draft.origin],
      target =
        draft.action === "connect"
          ? this.view.points[draft.target]
          : draft.point;
    if (!origin || !target) return;
    ctx.strokeStyle = "#f5dc9b";
    ctx.globalAlpha = 0.8;
    ctx.setLineDash([5, 5]);
    ctx.beginPath();
    arc(origin, target).forEach((v, i) => {
      const p = this.point(v);
      if (!i) ctx.moveTo(p.x, p.y);
      else ctx.lineTo(p.x, p.y);
    });
    ctx.stroke();
    ctx.setLineDash([]);
  }
  destroy(): void {
    this.stopped = true;
    cancelAnimationFrame(this.frame);
    this.frame = 0;
    this.controller.abort();
    this.resize.disconnect();
    this.intersection.disconnect();
  }
}
