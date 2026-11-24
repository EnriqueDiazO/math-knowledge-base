import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import { fireEvent, getByRole, getByLabelText, getAllByRole } from '@testing-library/dom';
import { renderRoom } from '../src/knowledge-map/room';
import type { Bridge } from '../src/knowledge-map/component';
import type { Data, Intent, SavedView } from '../src/knowledge-map/model';
import { studyState, freshView } from '../src/knowledge-map/model';
let parent: HTMLDivElement, dispose: (()=>void) | undefined;
function fixture(): Data {
  const nodes=['a@Uno','a@Dos','b@Uno'].map(key=>({key,id:key.split('@')[0],source:key.split('@')[1],titulo:'Mismo título',tipo:'nota',contenido_latex:'Contenido',comentario:'',categorias:[],revision:'r'}));
  const views: SavedView[]=['Uno','Dos'].map((name,i)=>({uid:crypto.randomUUID(),name:'Esfera '+name,revision:'v'+i,state:{...studyState(freshView()),members:i?['a@Uno','b@Uno']:['a@Uno','a@Dos']}}));
  const state={version:1 as const,name:'Habitación canónica',document_id:'doc',note_id:'',goal_view_uid:'',goal_id:'',spheres:views.map((v,i)=>({view_uid:v.uid,position:[.25+.5*i,.45] as [number,number]}))};
  return {scope:crypto.randomUUID(),nodes,edges:[],sources:[{id:'source',name:'Fuente'}],concept_types:['nota'],relation_types:[],views,rooms:[{uid:crypto.randomUUID(),revision:'room-rev',state}],
    documents:[{document_id:'doc',source_id:'source',reference_id:'ref',title:'Edición en PDF',kind:'pdf'}],
    annotations:[{annotation_id:'mark',document_id:'doc',source_id:'source',reference_id:'ref',page_number:18,page_label:'xii',quote_text:'Pasaje exacto',body:'Comentario',kind:'highlight'}],notes:[]};
}
const leaf = vi.fn<(bridge:Bridge)=>()=>void>();
const trigger = vi.fn<(key:string,value:unknown)=>void>();
function mount(data:Data) { dispose?.();dispose=renderRoom({parentElement:parent,data,setTriggerValue:trigger},leaf); }
function click(name:string) {fireEvent.click(getByRole(parent,'button',{name}));}
function choose(name:string,value:string){fireEvent.change(getByLabelText(parent,name),{target:{value}});}
beforeEach(()=>{parent=document.createElement('div');document.body.append(parent);localStorage.clear();leaf.mockReset().mockImplementation(()=>()=>{});trigger.mockReset();});
afterEach(()=>{dispose?.();dispose=undefined;parent.remove();});
it('loads confirmed room references without writes and removes only a visual reference',()=>{
  const data=fixture(),before=structuredClone(data);mount(data);
  expect(parent.querySelectorAll('.room-sphere')).toHaveLength(2);expect(trigger).not.toHaveBeenCalled();
  fireEvent.click(getAllByRole(parent,'button',{name:'Quitar referencia a esta esfera'})[0]);
  expect(parent.querySelectorAll('.room-sphere')).toHaveLength(1);expect(data).toEqual(before);expect(trigger).not.toHaveBeenCalled();
  expect(parent.textContent).toContain('Disposición local sin guardar');
});
it('opens the canonical reader and the same note editor with exact annotation identity',()=>{
  const data=fixture();mount(data);click('Abrir fuente en el lector');
  expect(trigger).toHaveBeenLastCalledWith('open_source',{document_id:'doc'});
  choose('Anotación o pasaje registrado','mark');expect(parent.querySelector('blockquote')?.textContent).toBe('Pasaje exacto');
  click('Volver al pasaje exacto');expect(trigger).toHaveBeenLastCalledWith('open_source',{document_id:'doc',annotation_id:'mark'});
  trigger.mockClear();click('Escribir nota desde este pasaje');
  const last=leaf.mock.calls.at(-1)![0];expect(last.initialDraft).toMatchObject({action:'save_note',annotationId:'mark',documentId:'doc',content:'Pasaje exacto',referenceLocator:{printed_page:'xii',pdf_page:18}});
  expect(last.draftMapUid).toBe(data.rooms![0].uid);expect(trigger).not.toHaveBeenCalled();
});
it('compares two independent views and synchronizes canonical selection, including narrow-screen pane state',async()=>{
  const data=fixture();mount(data);click('Comparar');
  const first=leaf.mock.calls.at(-2)![0],second=leaf.mock.calls.at(-1)![0];
  expect(first.data.nodes).toBe(second.data.nodes);expect(first.data.scope).not.toBe(second.data.scope);
  expect(first.initialView?.uid).not.toBe(second.initialView?.uid);
  const shared=getByRole(parent,'button',{name:'Mismo título · Uno · a'});fireEvent.click(shared);
  expect(leaf.mock.calls.at(-2)![0].selectionKey).toBe('a@Uno');expect(leaf.mock.calls.at(-1)![0].selectionKey).toBe('a@Uno');
  click('Mostrar Esfera Dos');expect(parent.querySelectorAll('.room-compare-pane')[1].getAttribute('data-active')).toBe('true');
  leaf.mock.calls.at(-1)![0].onSelect?.('b@Uno');await Promise.resolve();
  expect(leaf.mock.calls.at(-2)![0].selectionKey).toBe('b@Uno');expect(trigger).not.toHaveBeenCalled();
});
it('takes an immutable room submission and leaves later local changes unsaved after acknowledgement',()=>{
  const data=fixture();mount(data);click('Guardar habitación');
  const [key,payload]=trigger.mock.calls[0] as [string,Intent];expect(key).toBe('intent');expect(payload.action).toBe('save_room');
  fireEvent.input(getByLabelText(parent,'Nombre de la habitación'),{target:{value:'Nombre posterior'}});
  expect(payload.room_state?.name).toBe('Habitación canónica');
  mount({...data,result:{operation_id:payload.operation_id,status:'saved',message:'Guardada',view_revision:'new-rev'}});
  expect(parent.textContent).toContain('Disposición local sin guardar');expect(parent.textContent).toContain('Nombre posterior');
  click('Guardar habitación');expect(trigger.mock.calls.at(-1)![1]).toMatchObject({revision:'new-rev',room_state:{name:'Nombre posterior'}});
});
it('moves room poses with a dedicated keyboard handle without touching a graph or writing to Mongo',()=>{
  const data=fixture(),before=structuredClone(data);mount(data);
  const card=parent.querySelector<HTMLElement>('.room-sphere')!;const original=card.style.left;
  fireEvent.keyDown(getByRole(parent,'button',{name:'Recolocar Esfera Uno'}),{key:'ArrowRight'});
  expect(card.style.left).not.toBe(original);expect(data).toEqual(before);expect(trigger).not.toHaveBeenCalled();
  mount(data);expect(parent.querySelector<HTMLElement>('.room-sphere')!.style.left).not.toBe(original);
});
it('creates a genuinely empty persisted view and adds its reference only after a matching acknowledgement',()=>{
  const data=fixture();mount(data);click('Crear y guardar esfera vacía');
  const intent=trigger.mock.calls[0][1] as Intent;
  expect(intent.view_state?.members).toEqual([]);expect(intent.view_state?.points).toEqual({});
  expect(parent.querySelectorAll('.room-sphere')).toHaveLength(2);
  mount({...data,result:{operation_id:intent.operation_id,status:'saved',message:'Vista creada',map_uid:intent.map_uid,view_revision:'view-rev'}});
  expect(parent.querySelectorAll('.room-sphere')).toHaveLength(3);
  expect(data.nodes).toHaveLength(3);expect(parent.textContent).toContain('Vista no disponible');
});
it("switches recoverable local rooms and prevents duplicate references without changing saved spheres", () => {
  const data = fixture(),
    before = structuredClone(data),
    original = data.rooms![0].uid;
  mount(data);
  choose("Añadir una vista guardada", data.views![0].uid);
  click("Añadir esta esfera a la habitación");
  expect(parent.querySelectorAll(".room-sphere")).toHaveLength(2);
  click("Nueva habitación local");
  expect(parent.querySelectorAll(".room-sphere")).toHaveLength(0);
  choose("Añadir una vista guardada", data.views![1].uid);
  click("Añadir esta esfera a la habitación");
  expect(parent.querySelectorAll(".room-sphere")).toHaveLength(1);
  choose("Abrir habitación", original);
  expect(parent.querySelectorAll(".room-sphere")).toHaveLength(2);
  expect(data).toEqual(before);
  expect(trigger).not.toHaveBeenCalled();
});
it("reconciles the exact pending request and adopts a reviewed revision without replacing local work", () => {
  const data = fixture();
  mount(data);
  fireEvent.input(getByLabelText(parent, "Nombre de la habitación"), {
    target: { value: "Trabajo propio" },
  });
  click("Guardar habitación");
  const intent = trigger.mock.calls.at(-1)![1] as Intent;
  click("Reconciliar el mismo envío");
  expect(trigger.mock.calls.at(-1)![1]).toEqual(intent);
  const remote = {
    ...data.rooms![0],
    revision: "remote-revision",
    state: { ...data.rooms![0].state, name: "Nombre remoto" },
  };
  mount({
    ...data,
    rooms: [remote],
    result: {
      operation_id: intent.operation_id,
      status: "conflict",
      message: "Otra ventana guardó la habitación.",
    },
  });
  click("He revisado: conservar mi disposición y adoptar esta revisión");
  click("Guardar habitación");
  expect(trigger.mock.calls.at(-1)![1]).toMatchObject({
    revision: "remote-revision",
    room_state: { name: "Trabajo propio" },
  });
  expect(data.rooms![0].state.name).toBe("Habitación canónica");
});
it("keeps the saved note, citation and goal identity when opening a contextual concept publication", () => {
  const data = fixture();
  data.notes = [
    {
      note_id: "note-owned",
      title: "Nota de trabajo",
      body: "Cuerpo $x$",
      source_id: "source",
      document_id: "doc",
      reference_id: "ref",
      revision: "note-revision",
      page_start: 18,
      page_end: 18,
      tags: [],
    },
  ];
  data.rooms![0].state.note_id = "note-owned";
  data.views![0].state.goals = [
    {
      id: "goal-owned",
      label: "Pregunta propia",
      point: [1, 0, 0],
      state: "working",
      draftId: "",
      conceptKey: "",
    },
  ];
  const before = structuredClone(data);
  mount(data);
  click("Abrir fuente de esta nota");
  expect(trigger).toHaveBeenLastCalledWith("open_source", {
    document_id: "doc",
    note_id: "note-owned",
  });
  trigger.mockClear();
  choose("Pregunta que completa esta nota (opcional)", "goal-owned");
  click("Incorporar nota como concepto…");
  const bridge = leaf.mock.calls.at(-1)![0];
  expect(bridge.initialDraft).toMatchObject({
    action: "publish_note",
    noteId: "note-owned",
    noteRevision: "note-revision",
    goalId: "goal-owned",
    point: [1, 0, 0],
    content: "Cuerpo $x$",
    referenceId: "ref",
  });
  bridge.onSaved?.(
    { status: "saved", message: "Concepto incorporado" },
    bridge.initialDraft!,
  );
  expect(parent.textContent).not.toContain("Disposición guardada");
  expect(trigger).not.toHaveBeenCalled();
  expect(data).toEqual(before);
});
it("opens unresolved questions as drafts and completed questions at their canonical concept", () => {
  const data = fixture();
  data.views![0].state.goals = [
    {
      id: "question",
      label: "Por demostrar",
      point: [0, 1, 0],
      state: "pending",
      draftId: "durable-goal-draft",
      conceptKey: "",
    },
    {
      id: "answered",
      label: "Pregunta resuelta",
      point: [0, 0, 1],
      state: "reviewed",
      draftId: "",
      conceptKey: "a@Uno",
    },
  ];
  const before = structuredClone(data);
  mount(data);
  click("Por demostrar · pending · Esfera Uno");
  let bridge = leaf.mock.calls.at(-1)![0];
  expect(bridge.initialDraft).toMatchObject({
    action: "create",
    id: "durable-goal-draft",
    title: "Por demostrar",
    goalId: "question",
    point: [0, 1, 0],
  });
  bridge.onExit?.();
  click("Pregunta resuelta · reviewed · Esfera Uno");
  bridge = leaf.mock.calls.at(-1)![0];
  expect(bridge.selectionKey).toBe("a@Uno");
  expect(data).toEqual(before);
  expect(trigger).not.toHaveBeenCalled();
});
it("keeps an unconfirmed note workspace open and never treats an invalid response as a saved note", async () => {
  const data = fixture();
  data.documents = [];
  data.rooms![0].state.document_id = "";
  mount(data);
  click("Abrir libro de estudio");
  expect(trigger).toHaveBeenLastCalledWith("open_library", {});
  trigger.mockClear();
  click("Escribir nota personal");
  const bridge = leaf.mock.calls.at(-1)![0];
  expect(parent.querySelector(".room-note-workspace")).not.toBeNull();
  bridge.onSaved?.(
    { status: "invalid", message: "No guardada" },
    bridge.initialDraft!,
  );
  await Promise.resolve();
  expect(parent.querySelector(".room-note-workspace")).not.toBeNull();
  bridge.onSaved?.(
    { status: "saved", message: "Nota confirmada", note_id: "confirmed-note" },
    bridge.initialDraft!,
  );
  await Promise.resolve();
  expect(parent.querySelector(".room-note-workspace")).toBeNull();
  expect(parent.textContent).toContain("Nota confirmada");
  expect(trigger).not.toHaveBeenCalled();
});
