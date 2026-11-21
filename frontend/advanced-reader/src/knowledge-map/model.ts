import type { Camera, Vec } from './geometry';
export type Node = { key: string; id: string; source: string; titulo: string; tipo: string; contenido_latex: string; comentario: string; categorias: string[]; revision: string };
export type Edge = { key: string; from: string; to: string; tipo: string; descripcion: string };
export type Intent = { operation_id: string; action: 'create' | 'create_connected' | 'connect' | 'edit'; key?: string; target?: string; source_id?: string; titulo?: string; tipo?: string; contenido_latex?: string; comentario?: string; categorias?: string[]; revision?: string; relation_type?: string; reverse?: boolean };
export type Result = { operation_id?: string; status: string; message: string; key?: string };
export type Data = { nodes: Node[]; edges: Edge[]; sources: { id: string; name: string }[]; concept_types: string[]; relation_types: string[]; scope: string; result?: Result };
export type Draft = { action: Intent['action']; title: string; content: string; comment: string; categories: string; source: string; type: string; origin: string; target: string; relation: string; reverse: boolean; revision: string; point: Vec };
export type View = { camera: Camera; flat: boolean; selected: string; source: string; type: string; relation: string; points: Record<string, Vec>; draft?: Draft; pending?: Intent; status?: Result; auto: boolean; acknowledged?: string };
export function freshView(): View {
  return { camera: { yaw: 0, pitch: 0, zoom: 1 }, flat: false, selected: '', source: '', type: '', relation: '', points: {}, auto: false };
}
export function visibleNodes(data: Data, view: View): Node[] {
  return data.nodes.filter(n => (!view.source || n.source === view.source) && (!view.type || n.tipo === view.type));
}
export function visibleEdges(data: Data, nodes: Node[], view: View): Edge[] {
  const keys = new Set(nodes.map(n => n.key));
  return data.edges.filter(e => keys.has(e.from) && keys.has(e.to) && (!view.relation || e.tipo === view.relation));
}
export function neighbors(data: Data, key: string): Node[] {
  const keys = new Set<string>();
  data.edges.forEach(e => { if (e.from === key) keys.add(e.to); if (e.to === key) keys.add(e.from); });
  return data.nodes.filter(n => keys.has(n.key));
}
export function draftFor(data: Data, view: View, action: Draft['action'], point: Vec): Draft {
  const node = data.nodes.find(n => n.key === view.selected);
  return { action, title: action === 'edit' ? node?.titulo ?? '' : '', content: action === 'edit' ? node?.contenido_latex ?? '' : '', comment: action === 'edit' ? node?.comentario ?? '' : '', categories: action === 'edit' ? node?.categorias.join(', ') ?? '' : '', source: data.sources[0]?.id ?? '', type: 'nota', origin: node?.key ?? '', target: '', relation: 'requiere_concepto', reverse: false, revision: node?.revision ?? '', point };
}
export function intention(draft: Draft, operationId: string): Intent {
  if (draft.action === 'connect') return { operation_id: operationId, action: 'connect', key: draft.origin, target: draft.target, relation_type: draft.relation, reverse: draft.reverse };
  return { operation_id: operationId, action: draft.action, key: draft.origin, source_id: draft.source, titulo: draft.title, tipo: draft.type, contenido_latex: draft.content, comentario: draft.comment, categorias: draft.categories.split(',').map(s => s.trim()).filter(Boolean), revision: draft.revision, relation_type: draft.relation, reverse: draft.reverse };
}
export function acceptResult(data: Data, view: View): void {
  const result = data.result;
  if (!result || result.operation_id !== view.pending?.operation_id) return;
  view.status = result;
  if (result.status === 'saved' || result.status === 'duplicate') {
    if (result.key) view.selected = result.key;
    view.acknowledged = result.operation_id;
    view.pending = undefined;
    view.draft = undefined;
  } else if (result.status === 'conflict' || result.status === 'invalid') view.pending = undefined;
}
