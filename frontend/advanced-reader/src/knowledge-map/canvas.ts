import { arc, focus, project, surface } from './geometry';
import type { Vec, Point } from './geometry';
import { visibleEdges, visibleNodes } from './model';
import type { Data, View, Node } from './model';
export const colors: Record<string, string> = { definicion: '#65e5ce', teorema: '#ffe29a', proposicion: '#7abfff', corolario: '#d0b4ff', lema: '#ffa3b5', ejemplo: '#ffbd72', nota: '#bfccd9' };
export class MapCanvas {
  private context: CanvasRenderingContext2D;
  private width = 600;
  private height = 470;
  private frame = 0;
  private lastTime = 0;
  private shown = true;
  private stopped = false;
  private hover = '';
  private drag?: { x: number; y: number; moved: boolean };
  private nodes: Node[] = [];
  private paths: { from: string; to: string; points: Vec[] }[] = [];
  private projected = new Map<string, Point>();
  private controller = new AbortController();
  private resize: ResizeObserver;
  private intersection: IntersectionObserver;
  private motion = window.matchMedia('(prefers-reduced-motion: reduce)');
  constructor(private canvas: HTMLCanvasElement, private data: Data, private view: View,
    private select: (key: string) => void, private create: (point: Vec) => void,
    private changed: () => void) {
    const ctx = canvas.getContext('2d');
    if (!ctx) throw new Error('Canvas no disponible; usa los formularios accesibles.');
    this.context = ctx;
    const options = { signal: this.controller.signal };
    canvas.addEventListener('pointerdown', e => { this.pause(); this.drag = { x: e.clientX, y: e.clientY, moved: false }; canvas.setPointerCapture(e.pointerId); }, options);
    canvas.addEventListener('pointermove', e => this.move(e), options);
    canvas.addEventListener('pointerup', e => this.up(e), options);
    canvas.addEventListener('pointercancel', () => { this.drag = undefined; }, options);
    canvas.addEventListener('pointerleave', () => { this.hover = ''; this.request(); }, options);
    canvas.addEventListener('contextmenu', e => { e.preventDefault(); this.pause(); const r = canvas.getBoundingClientRect(); this.create(surface(e.clientX - r.left, e.clientY - r.top, view.camera, this.width, this.height)); }, options);
    canvas.addEventListener('keydown', e => this.keyboard(e), options);
    document.addEventListener('visibilitychange', () => this.request(), options);
    this.motion.addEventListener('change', () => { this.pause(); this.request(); }, options);
    this.resize = new ResizeObserver(entries => {
      this.width = Math.max(200, entries[0].contentRect.width);
      const dpr = Math.min(window.devicePixelRatio || 1, 2);
      canvas.width = this.width * dpr; canvas.height = this.height * dpr;
      this.context.setTransform(dpr, 0, 0, dpr, 0, 0); this.request();
    });
    this.resize.observe(canvas);
    this.intersection = new IntersectionObserver(entries => { this.shown = entries[0].isIntersecting; this.request(); });
    this.intersection.observe(canvas);
    this.update(data);
  }
  update(data: Data): void {
    this.data = data;
    this.nodes = visibleNodes(data, this.view);
    const lanes = new Map<string, number>();
    this.paths = visibleEdges(data, this.nodes, this.view).map(edge => {
      const pair = [edge.from, edge.to].sort().join('\u0000');
      const lane = lanes.get(pair) ?? 0; lanes.set(pair, lane + 1);
      return { from: edge.from, to: edge.to, points: arc(this.view.points[edge.from], this.view.points[edge.to], lane, edge.from === edge.to) };
    });
    this.canvas.dataset.nodes = String(this.nodes.length); this.canvas.dataset.edges = String(this.paths.length);
    this.request();
  }
  pause(): void { this.view.auto = false; }
  request(): void {
    if (!this.frame && !this.stopped) this.frame = requestAnimationFrame(time => this.draw(time));
  }
  private move(e: PointerEvent): void {
    if (this.drag) {
      const dx = e.clientX - this.drag.x, dy = e.clientY - this.drag.y;
      if (Math.abs(dx) + Math.abs(dy) > 2) this.drag.moved = true;
      this.view.camera.yaw += dx * .007; this.view.camera.pitch += dy * .007;
      this.drag.x = e.clientX; this.drag.y = e.clientY; this.changed();
    } else {
      const r = this.canvas.getBoundingClientRect(); this.hover = this.hit(e.clientX - r.left, e.clientY - r.top);
    }
    this.request();
  }
  private up(e: PointerEvent): void {
    const moved = this.drag?.moved; this.drag = undefined;
    this.canvas.releasePointerCapture(e.pointerId);
    if (!moved) {
      const rect = this.canvas.getBoundingClientRect();
      const key = this.hit(e.clientX - rect.left, e.clientY - rect.top);
      if (key) this.select(key);
    }
    this.changed();
  }
  private hit(x: number, y: number): string {
    let key = '', depth = -2;
    this.projected.forEach((p, id) => { if (Math.hypot(p.x - x, p.y - y) < 15 && p.z > depth) { key = id; depth = p.z; } });
    return key;
  }
  private keyboard(e: KeyboardEvent): void {
    const delta: Record<string, [number, number]> = { ArrowLeft: [-.12, 0], ArrowRight: [.12, 0], ArrowUp: [0, -.12], ArrowDown: [0, .12] };
    if (!delta[e.key]) return;
    e.preventDefault(); this.pause(); this.view.camera.yaw += delta[e.key][0]; this.view.camera.pitch += delta[e.key][1];
    this.changed(); this.request();
  }
  bringFront(key: string): void {
    this.pause(); this.view.camera = focus(this.view.points[key], this.view.camera); this.request();
  }
  private draw(time: number): void {
    this.frame = 0;
    if (this.stopped || document.hidden || !this.shown) { this.lastTime = 0; return; }
    const start = performance.now(), ctx = this.context, camera = this.view.camera;
    const animate = this.view.auto && !this.view.draft && !this.view.selected && !this.motion.matches && !this.view.flat;
    if (animate && this.lastTime) camera.yaw += Math.min(time - this.lastTime, 50) * .000045;
    this.lastTime = time;
    ctx.clearRect(0, 0, this.width, this.height);
    const r = Math.min(this.width, this.height) * .38 * camera.zoom;
    ctx.strokeStyle = '#26485c'; ctx.lineWidth = 1;
    if (!this.view.flat) { ctx.beginPath(); ctx.arc(this.width / 2, this.height / 2, r, 0, Math.PI * 2); ctx.stroke(); }
    this.drawEdges(ctx);
    this.projected.clear();
    const projected = this.nodes.map(node => ({ node, point: project(this.view.points[node.key], camera, this.width, this.height, this.view.flat) })).sort((a, b) => a.point.z - b.point.z);
    projected.forEach(({ node, point }) => this.drawNode(ctx, node, point));
    this.drawProposal(ctx);
    if (this.view.draft && this.view.draft.action.startsWith('create')) {
      const p = project(this.view.draft.point, camera, this.width, this.height, this.view.flat);
      ctx.globalAlpha = .9; ctx.strokeStyle = '#ffffff'; ctx.setLineDash([4, 4]); ctx.beginPath(); ctx.arc(p.x, p.y, 12, 0, Math.PI * 2); ctx.stroke(); ctx.setLineDash([]);
      ctx.fillStyle = '#ffffff'; ctx.fillText('Borrador', p.x + 16, p.y);
    }
    ctx.globalAlpha = 1;
    this.canvas.dataset.renderMs = String(performance.now() - start);
    if (animate) this.request();
  }
  private drawProposal(ctx: CanvasRenderingContext2D): void {
    const draft = this.view.draft;
    if (!draft || !['connect', 'create_connected'].includes(draft.action)) return;
    const origin = this.view.points[draft.origin];
    const target = draft.action === 'connect' ? this.view.points[draft.target] : draft.point;
    if (!origin || !target) return;
    ctx.globalAlpha = .85; ctx.strokeStyle = '#f5dc9b'; ctx.lineWidth = 2; ctx.setLineDash([5, 5]); ctx.beginPath();
    arc(origin, target).forEach((v, i) => { const p = project(v, this.view.camera, this.width, this.height, this.view.flat); if (i === 0) ctx.moveTo(p.x, p.y); else ctx.lineTo(p.x, p.y); });
    ctx.stroke(); ctx.setLineDash([]);
  }
  private drawEdges(ctx: CanvasRenderingContext2D): void {
    const projected = this.paths.map(path => ({
      strong: [this.hover, this.view.selected].some(key => !!key && (path.from === key || path.to === key)),
      points: path.points.map(v => project(v, this.view.camera, this.width, this.height, this.view.flat)),
    }));
    // Four strokes per frame, rather than one stroke per arc segment. Projection
    // is still O(nodes + stored edges), with no pairwise semantic inference.
    for (const strong of [false, true]) for (const back of [true, false]) {
      ctx.lineWidth = strong ? 1.8 : .8; ctx.strokeStyle = strong ? '#71f6e0' : '#4b8194';
      ctx.globalAlpha = back ? .12 : strong ? .9 : .45; ctx.beginPath();
      projected.filter(path => path.strong === strong).forEach(path => {
        for (let i = 1; i < path.points.length; i++) {
          const a = path.points[i - 1], b = path.points[i];
          if ((b.z < 0) !== back || (this.view.flat && Math.abs(a.x - b.x) > this.width * .35)) continue;
          ctx.moveTo(a.x, a.y); ctx.lineTo(b.x, b.y);
        }
        const tip = path.points[path.points.length - 3], prev = path.points[path.points.length - 4];
        if ((tip.z < 0) === back) {
          const angle = Math.atan2(tip.y - prev.y, tip.x - prev.x);
          ctx.moveTo(tip.x - 6 * Math.cos(angle - .5), tip.y - 6 * Math.sin(angle - .5)); ctx.lineTo(tip.x, tip.y); ctx.lineTo(tip.x - 6 * Math.cos(angle + .5), tip.y - 6 * Math.sin(angle + .5));
        }
      });
      ctx.stroke();
    }
  }
  private drawNode(ctx: CanvasRenderingContext2D, node: Node, p: Point): void {
    this.projected.set(node.key, p);
    const selected = node.key === this.view.selected, active = selected || node.key === this.hover;
    ctx.globalAlpha = p.z < 0 ? .25 : .6 + .4 * p.z;
    ctx.fillStyle = colors[node.tipo] ?? '#bfccd9';
    ctx.beginPath(); ctx.arc(p.x, p.y, active ? 7 : 3 + (p.z + 1), 0, Math.PI * 2); ctx.fill();
    if (selected) { ctx.strokeStyle = '#ffffff'; ctx.lineWidth = 2; ctx.beginPath(); ctx.arc(p.x, p.y, 11, 0, Math.PI * 2); ctx.stroke(); }
    if (active || (this.nodes.length < 35 && p.z > .1)) {
      ctx.fillStyle = '#edf9ff'; ctx.font = active ? 'bold 13px system-ui' : '12px system-ui';
      const title = node.titulo.length > 37 ? node.titulo.slice(0, 35) + '…' : node.titulo;
      ctx.fillText(title, Math.max(4, Math.min(p.x + 13, this.width - ctx.measureText(title).width - 4)), p.y - 9);
    }
  }
  destroy(): void {
    this.stopped = true; cancelAnimationFrame(this.frame); this.frame = 0;
    this.controller.abort(); this.resize.disconnect(); this.intersection.disconnect();
  }
}
