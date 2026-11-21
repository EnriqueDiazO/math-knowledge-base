import type { EditorSnapshot } from "./document-editor";
import type { Camera, Vec } from "./geometry";
export type Node = {
  key: string;
  id: string;
  source: string;
  titulo: string;
  tipo: string;
  contenido_latex: string;
  comentario: string;
  categorias: string[];
  revision: string;
  referencia?: Record<string, string>;
};
export type Edge = {
  key: string;
  from: string;
  to: string;
  tipo: string;
  descripcion: string;
};
export type Intent = {
  operation_id: string;
  action: "create" | "create_connected" | "connect" | "edit" | "save_view";
  map_uid?: string;
  map_name?: string;
  view_state?: StudyState;
  key?: string;
  target?: string;
  source_id?: string;
  titulo?: string;
  tipo?: string;
  contenido_latex?: string;
  comentario?: string;
  categorias?: string[];
  revision?: string;
  relation_type?: string;
  reverse?: boolean;
};
export type Goal = {
  id: string;
  label: string;
  point: Vec;
  state: "pending" | "working" | "reviewed";
  draftId: string;
  conceptKey: string;
};
export type StudyState = {
  version: 1;
  points: Record<string, Vec>;
  flatPoints: Record<string, [number, number]>;
  pinned: string[];
  areas: string[];
  mandala: boolean;
  goals: Goal[];
};
export type SavedView = {
  uid: string;
  name: string;
  revision: string;
  state: StudyState;
};
export type Result = {
  operation_id?: string;
  status: string;
  message: string;
  key?: string;
  map_uid?: string;
  view_revision?: string;
};
export type Data = {
  nodes: Node[];
  edges: Edge[];
  sources: { id: string; name: string }[];
  concept_types: string[];
  relation_types: string[];
  scope: string;
  views?: SavedView[];
  result?: Result;
};
export type Draft = {
  id?: string;
  updated?: number;
  completed?: boolean;
  document?: EditorSnapshot;
  goalId?: string;
  submitted?: boolean;
  action: "create" | "create_connected" | "connect" | "edit";
  title: string;
  content: string;
  comment: string;
  categories: string;
  source: string;
  type: string;
  origin: string;
  target: string;
  relation: string;
  reverse: boolean;
  revision: string;
  point: Vec;
};
export type View = {
  mapUid?: string;
  mapName?: string;
  viewRevision?: string;
  layoutDirty?: boolean;
  flatPoints?: Record<string, [number, number]>;
  pinned?: string[];
  areas?: string[];
  mandala?: boolean;
  goals?: Goal[];
  neighborhood?: boolean;
  focusedEdge?: string;
  frontOnly?: boolean;
  expanded?: boolean;
  reader?: string;
  textSize?: number;
  camera: Camera;
  flat: boolean;
  selected: string;
  source: string;
  type: string;
  relation: string;
  points: Record<string, Vec>;
  draft?: Draft;
  pending?: Intent;
  status?: Result;
  auto: boolean;
  acknowledged?: string;
};
export function freshView(): View {
  return {
    camera: { yaw: 0, pitch: 0, zoom: 1 },
    flat: false,
    selected: "",
    source: "",
    type: "",
    relation: "",
    points: {},
    auto: false,
  };
}
export function visibleNodes(data: Data, view: View): Node[] {
  const adjacent =
    view.neighborhood && view.selected
      ? new Set([
          view.selected,
          ...neighbors(data, view.selected).map((n) => n.key),
        ])
      : undefined;
  return data.nodes.filter(
    (n) =>
      (!adjacent || adjacent.has(n.key)) &&
      (!view.source || n.source === view.source) &&
      (!view.type || n.tipo === view.type),
  );
}
export function visibleEdges(data: Data, nodes: Node[], view: View): Edge[] {
  const keys = new Set(nodes.map((n) => n.key));
  return data.edges.filter(
    (e) =>
      keys.has(e.from) &&
      keys.has(e.to) &&
      (!view.relation || e.tipo === view.relation),
  );
}
export function neighbors(data: Data, key: string): Node[] {
  const keys = new Set<string>();
  data.edges.forEach((e) => {
    if (e.from === key) keys.add(e.to);
    if (e.to === key) keys.add(e.from);
  });
  return data.nodes.filter((n) => keys.has(n.key));
}
export function draftFor(
  data: Data,
  view: View,
  action: Draft["action"],
  point: Vec,
): Draft {
  const node = data.nodes.find((n) => n.key === view.selected);
  return {
    action,
    title: action === "edit" ? (node?.titulo ?? "") : "",
    content: action === "edit" ? (node?.contenido_latex ?? "") : "",
    comment: action === "edit" ? (node?.comentario ?? "") : "",
    categories: action === "edit" ? (node?.categorias.join(", ") ?? "") : "",
    source: data.sources[0]?.id ?? "",
    type: "nota",
    origin: node?.key ?? "",
    target: "",
    relation: "requiere_concepto",
    reverse: false,
    revision: node?.revision ?? "",
    point,
  };
}
export function intention(draft: Draft, operationId: string): Intent {
  if (draft.action === "connect")
    return {
      operation_id: operationId,
      action: "connect",
      key: draft.origin,
      target: draft.target,
      relation_type: draft.relation,
      reverse: draft.reverse,
    };
  return {
    operation_id: operationId,
    action: draft.action,
    key: draft.origin,
    source_id: draft.source,
    titulo: draft.title,
    tipo: draft.type,
    contenido_latex: draft.content,
    comentario: draft.comment,
    categorias: draft.categories
      .split(",")
      .map((s) => s.trim())
      .filter(Boolean),
    revision: draft.revision,
    relation_type: draft.relation,
    reverse: draft.reverse,
  };
}
export function acceptResult(data: Data, view: View): void {
  const result = data.result;
  if (!result || result.operation_id !== view.pending?.operation_id) return;
  view.status = result;
  if (result.status === "saved" || result.status === "duplicate") {
    if (result.key) view.selected = result.key;
    view.acknowledged = result.operation_id;
    view.pending = undefined;
    view.draft = undefined;
  } else if (result.status === "conflict" || result.status === "invalid")
    view.pending = undefined;
}

export function studyState(view: View): StudyState {
  return {
    version: 1,
    points: view.points,
    flatPoints: view.flatPoints ?? {},
    pinned: view.pinned ?? [],
    areas: view.areas ?? [],
    mandala: !!view.mandala,
    goals: view.goals ?? [],
  };
}
export function useSavedView(view: View, saved: SavedView): void {
  view.mapUid = saved.uid;
  view.mapName = saved.name;
  view.viewRevision = saved.revision;
  Object.assign(view, structuredClone(saved.state));
  view.layoutDirty = false;
}
