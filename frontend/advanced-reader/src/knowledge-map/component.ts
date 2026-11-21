import './style.css';
import { MapCanvas, colors } from './canvas';
import { positions, unrotate } from './geometry';
import type { Vec } from './geometry';
import { acceptResult, draftFor, freshView, intention, neighbors, visibleNodes } from './model';
import type { Data, Draft, View } from './model';

type Bridge = { parentElement: HTMLElement; data: Data; setTriggerValue: (key: string, value: unknown) => void };
const memory = new Map<string, View>();
const mounted = new WeakMap<HTMLElement, () => void>();
function element<K extends keyof HTMLElementTagNameMap>(tag: K, text = '', className = ''): HTMLElementTagNameMap[K] {
  const node = document.createElement(tag); node.textContent = text; node.className = className; return node;
}
function button(text: string, action: () => void, parent: HTMLElement, primary = false): HTMLButtonElement {
  const node = element('button', text, primary ? 'primary' : ''); node.type = 'button'; node.onclick = action; parent.append(node); return node;
}
function field(parent: HTMLElement, labelText: string, value: string, update: (value: string) => void, multiline = false): HTMLInputElement | HTMLTextAreaElement {
  const label = element('label', labelText), input = multiline ? element('textarea') : element('input');
  input.setAttribute('aria-label', labelText); input.value = value; input.oninput = () => update(input.value); label.append(input); parent.append(label); return input;
}
function selector(parent: HTMLElement, labelText: string, options: { value: string; text: string }[], value: string, update: (value: string) => void): HTMLSelectElement {
  const label = element('label', labelText), select = element('select');
  options.forEach(option => { const node = element('option', option.text); node.value = option.value; select.append(node); });
  select.setAttribute('aria-label', labelText); select.value = value; select.onchange = () => update(select.value); label.append(select); parent.append(label); return select;
}
function readView(scope: string): View {
  if (memory.has(scope)) return memory.get(scope)!;
  try {
    const parsed = JSON.parse(sessionStorage.getItem('mathmongo-map-' + scope) ?? 'null') as View | null;
    if (parsed && parsed.camera && ['yaw', 'pitch', 'zoom'].every(key => Number.isFinite(parsed.camera[key as keyof typeof parsed.camera])) && parsed.points) return parsed;
  } catch { /* Browser storage is optional; persistence of knowledge is server-side. */ }
  return freshView();
}
export default function render(bridge: Bridge): () => void {
  const { parentElement, data, setTriggerValue } = bridge;
  mounted.get(parentElement)?.();
  const view = readView(data.scope); memory.set(data.scope, view);
  const insertion = view.pending && data.result?.key && view.draft ? { key: data.result.key, point: view.draft.point } : undefined;
  view.points = positions(data.nodes.map(n => n.key), view.points, insertion);
  acceptResult(data, view);
  if (view.pending && data.result?.operation_id !== view.pending.operation_id) view.status = { status: 'uncertain', message: 'Existe un envío anterior sin confirmar. Reconcilia el mismo intento antes de continuar.' };
  const save = () => { try { sessionStorage.setItem('mathmongo-map-' + data.scope, JSON.stringify(view)); } catch { /* Retain in memory when storage is disabled/full. */ } };
  const root = element('section', '', 'knowledge-map'); root.setAttribute('aria-label', 'Mapa de conocimiento editable');
  const title = element('div', 'Una idea abre un camino', 'eyebrow'); root.append(title, element('h2', 'Tu conocimiento, conectado'));
  const toolbar = element('div', '', 'toolbar'), layout = element('div', '', 'layout'), stage = element('div', '', 'stage'), aside = element('aside');
  const canvas = element('canvas'); canvas.tabIndex = 0; canvas.setAttribute('role', 'img'); canvas.setAttribute('aria-label', 'Superficie del conocimiento. Flechas para girar; usa el selector para elegir conceptos.');
  const status = element('div', '', 'status'); status.setAttribute('role', 'status'); status.setAttribute('aria-live', 'polite');
  const filters = element('div', '', 'filters');
  root.append(toolbar, filters, status, layout); layout.append(stage, aside); stage.append(canvas);
  stage.append(element('p', 'Arrastra para girar · flechas con el mapa enfocado · clic derecho para crear aquí', 'hint'));
  const legend = element('div', '', 'legend');
  Object.entries(colors).forEach(([type, color]) => { const item = element('span', type); item.style.setProperty('--node-color', color); legend.append(item); });
  stage.append(legend);
  const host = parentElement.querySelector('.knowledge-map-root') ?? parentElement;
  host.replaceChildren(root);
  let timer: ReturnType<typeof setTimeout> | undefined;
  const scene = new MapCanvas(canvas, data, view, key => select(key), point => start('create', point), () => { save(); if (autoButton) autoButton.textContent = view.auto ? 'Pausar giro' : 'Giro suave'; });
  const redraw = () => { scene.update(data); save(); };
  const select = (key: string) => {
    if (view.draft) { view.status = { status: 'draft', message: 'Conserva o cancela el borrador antes de cambiar la selección.' }; renderStatus(); return; }
    view.selected = key; selectBox.value = key; scene.bringFront(key); renderAside(); redraw(); renderStatus();
  };
  const start = (action: Draft['action'], point: Vec = unrotate([0, 0, 1], view.camera)) => {
    if (view.pending || view.draft) return;
    scene.pause(); const candidate = positions([...data.nodes.map(n => n.key), '__draft__'], view.points, { key: '__draft__', point }).__draft__; view.draft = draftFor(data, view, action, candidate); view.status = { status: 'draft', message: 'Borrador: aún no se ha escrito en la base.' }; renderAside(); renderStatus(); redraw();
  };
  const refresh = () => { renderAside(); renderStatus(); redraw(); };
  const send = () => {
    if (!view.draft || view.pending) return;
    view.pending = intention(view.draft, crypto.randomUUID()); submitPending();
  };
  const submitPending = () => {
    if (!view.pending) return;
    view.status = { status: 'saving', message: 'Guardando… espera la confirmación. El envío ya no se puede cancelar.' };
    save(); renderStatus(); renderAside();
    setTriggerValue('intent', view.pending);
    timer = setTimeout(() => { view.status = { status: 'uncertain', message: 'La confirmación tarda. Reconcilia el mismo intento antes de crear otro.' }; save(); renderStatus(); renderAside(); }, 15000);
  };
  function renderStatus(): void {
    if (autoButton) { autoButton.textContent = view.auto ? 'Pausar giro' : 'Giro suave'; autoButton.disabled = !!view.draft; }
    status.replaceChildren(); status.dataset.state = view.status?.status ?? 'ready';
    status.append(element('span', view.status?.message ?? `${data.nodes.length} conceptos · ${data.edges.length} relaciones persistidas. Girar y filtrar no escribe en MongoDB.`));
    const selected = data.nodes.find(n => n.key === view.selected);
    if (selected && !visibleNodes(data, view).some(n => n.key === selected.key)) {
      status.append(element('p', 'El concepto está guardado y queda fuera de los filtros activos.'));
      button('Mostrar concepto guardado', () => { view.source = ''; view.type = ''; view.relation = ''; renderFilters(); refresh(); scene.bringFront(selected.key); }, status);
    }
    if (view.pending && ['uncertain', 'partial', 'pending'].includes(view.status?.status ?? '')) button('Reconciliar el mismo intento', submitPending, status, true);
  }
  function renderFilters(): void {
    filters.replaceChildren();
    const all = { value: '', text: 'Todos' };
    selector(filters, 'Fuente visible', [all, ...[...new Set(data.nodes.map(n => n.source))].sort().map(s => ({ value: s, text: s }))], view.source, value => { view.source = value; refresh(); });
    selector(filters, 'Tipo visible', [all, ...[...new Set(data.nodes.map(n => n.tipo))].sort().map(s => ({ value: s, text: s }))], view.type, value => { view.type = value; refresh(); });
    selector(filters, 'Relación visible', [all, ...data.relation_types.map(s => ({ value: s, text: s }))], view.relation, value => { view.relation = value; refresh(); });
  }
  function renderAside(): void {
    aside.replaceChildren();
    if (view.draft) { renderEditor(view.draft); return; }
    const selected = data.nodes.find(n => n.key === view.selected);
    if (!selected) { aside.append(element('h3', 'Encuentra una idea'), element('p', 'Selecciona un concepto o crea el primero sobre la esfera.')); return; }
    aside.append(element('h3', selected.titulo, 'selected-title'), element('p', `${selected.tipo} · ${selected.source}`, 'identity'), element('p', selected.key, 'identity'), element('p', selected.contenido_latex, 'content'));
    if (selected.comentario) aside.append(element('p', selected.comentario, 'content'));
    const actions = element('div', '', 'actions'); aside.append(actions);
    button('Editar ficha', () => start('edit'), actions, true);
    button('Crear conectado', () => start('create_connected', view.points[selected.key]), actions);
    button('Conectar con…', () => start('connect'), actions);
    button('Abrir nota / edición avanzada', () => { save(); setTriggerValue('open_note', { key: selected.key, nonce: crypto.randomUUID() }); }, actions);
    aside.append(element('h3', 'Vecinos reales'));
    const adjacent = neighbors(data, selected.key);
    if (!adjacent.length) aside.append(element('p', 'Todavía no tiene conexiones.'));
    adjacent.forEach(node => {
      const types = data.edges.filter(e => (e.from === selected.key && e.to === node.key) || (e.to === selected.key && e.from === node.key)).map(e => `${e.from === selected.key ? '→' : '←'} ${e.tipo}`);
      button(`${node.titulo} · ${types.join(', ')}`, () => select(node.key), aside).className = 'neighbor';
    });
  }
  function renderEditor(draft: Draft): void {
    const heading = { create: 'Crear concepto aquí', create_connected: 'Crear concepto conectado', connect: 'Conectar conceptos', edit: 'Editar ficha' }[draft.action];
    aside.append(element('h3', heading));
    const form = element('form'); form.onsubmit = e => { e.preventDefault(); send(); }; aside.append(form);
    const set = <K extends keyof Draft>(key: K, value: Draft[K]) => { draft[key] = value; save(); scene.request(); };
    if (draft.action !== 'connect') {
      const name = field(form, 'Nombre', draft.title, value => set('title', value)); name.required = true; name.maxLength = 500;
      if (draft.action !== 'edit') {
        selector(form, 'Source administrada', data.sources.map(s => ({ value: s.id, text: s.name })), draft.source, value => set('source', value));
        selector(form, 'Tipo de concepto', data.concept_types.map(s => ({ value: s, text: s })), draft.type, value => set('type', value));
        if (!data.sources.length) form.append(element('p', 'Crea una Source activa desde «Añadir Source» antes de guardar.', 'hint'));
      }
      const content = field(form, 'Contenido (texto o LaTeX)', draft.content, value => set('content', value), true); content.required = true; content.maxLength = 100000;
      const details = element('details'); details.append(element('summary', 'Opcionales')); form.append(details);
      field(details, 'Categorías separadas por comas', draft.categories, value => set('categories', value));
      field(details, 'Comentario', draft.comment, value => set('comment', value), true);
    }
    if (draft.action === 'connect' || draft.action === 'create_connected') relationFields(form, draft, set);
    if (view.status?.status === 'conflict' && draft.action === 'edit') button('Revisar versión actual y conservar mi borrador', () => {
      const node = data.nodes.find(n => n.key === draft.origin);
      if (node) {
        form.append(element('p', `Versión actual: ${node.titulo}\n${node.contenido_latex}`, 'content'));
        button('He revisado: basar mi borrador en esta versión', () => { draft.revision = node.revision; view.status = { status: 'draft', message: 'Versión revisada. El borrador sigue sin enviar.' }; refresh(); }, form);
      }
    }, form);
    const actions = element('div', '', 'actions'); form.append(actions);
    const submit = element('button', 'Guardar', 'primary'); submit.type = 'submit'; submit.disabled = !!view.pending || (draft.action.startsWith('create') && !data.sources.length); actions.append(submit);
    const cancel = button('Cancelar borrador', () => { if (!view.pending) { view.draft = undefined; view.status = { status: 'ready', message: 'Borrador cancelado; no se envió ninguna escritura.' }; refresh(); } }, actions); cancel.disabled = !!view.pending;
    if (view.pending) Array.from(form.querySelectorAll('input,textarea,select')).forEach(node => { (node as HTMLInputElement).disabled = true; });
  }
  function relationFields(form: HTMLElement, draft: Draft, set: <K extends keyof Draft>(key: K, value: Draft[K]) => void): void {
    if (draft.action === 'connect') selector(form, 'Destino', [{ value: '', text: 'Elegir concepto' }, ...data.nodes.map(n => ({ value: n.key, text: `${n.titulo} · ${n.source}` }))], draft.target, value => { set('target', value); preview(); });
    selector(form, 'Tipo de relación', data.relation_types.map(s => ({ value: s, text: s })), draft.relation, value => { set('relation', value); preview(); });
    const label = element('label', 'Invertir sentido '), reverse = element('input'); reverse.type = 'checkbox'; reverse.checked = draft.reverse; reverse.onchange = () => { set('reverse', reverse.checked); preview(); }; label.append(reverse); form.append(label);
    const proposed = element('p', '', 'preview'); form.append(proposed);
    function preview(): void {
      const left = data.nodes.find(n => n.key === draft.origin)?.titulo ?? draft.origin;
      const right = draft.action === 'connect' ? data.nodes.find(n => n.key === draft.target)?.titulo ?? 'Destino' : draft.title || 'Nuevo concepto';
      proposed.textContent = `${draft.reverse ? right : left} → [${draft.relation}] → ${draft.reverse ? left : right} · propuesta sin guardar`;
    }
    form.addEventListener('input', preview); preview();
  }
  const switchView = button(view.flat ? 'Esfera S²' : 'Plano', () => { view.flat = !view.flat; switchView.textContent = view.flat ? 'Esfera S²' : 'Plano'; refresh(); }, toolbar);
  button('Crear concepto aquí', () => start('create'), toolbar, true);
  const autoButton = button(view.auto ? 'Pausar giro' : 'Giro suave', () => { view.selected = ''; view.auto = !view.auto; refresh(); }, toolbar);
  button('− Zoom', () => { view.camera.zoom = Math.max(.5, view.camera.zoom - .15); redraw(); }, toolbar);
  button('+ Zoom', () => { view.camera.zoom = Math.min(2.5, view.camera.zoom + .15); redraw(); }, toolbar);
  button('Restablecer vista', () => { view.camera = { yaw: 0, pitch: 0, zoom: 1 }; scene.pause(); refresh(); }, toolbar);
  const searchBox = element('div', '', 'search'); toolbar.append(searchBox);
  const options = [{ value: '', text: 'Buscar o seleccionar concepto' }, ...data.nodes.map(n => ({ value: n.key, text: `${n.titulo} · ${n.source}` }))];
  // Search has no Python event; native selector provides a keyboard/touch fallback
  // for every node, including the back hemisphere and filtered concepts.
  const selectBox = selector(searchBox, 'Seleccionar concepto', options, view.selected, key => { if (key) select(key); });
  const search = field(searchBox, 'Buscar nombre o ID', '', query => {
    scene.pause(); selectBox.replaceChildren();
    options.filter(o => !o.value || (o.text + o.value).toLocaleLowerCase().includes(query.toLocaleLowerCase())).forEach(o => { const option = element('option', o.text); option.value = o.value; selectBox.append(option); });
  }); search.setAttribute('type', 'search');
  renderFilters(); renderAside(); renderStatus(); save();
  const cleanup = () => { scene.destroy(); if (timer) clearTimeout(timer); save(); };
  mounted.set(parentElement, cleanup); return cleanup;
}
