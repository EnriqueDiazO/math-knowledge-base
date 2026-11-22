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
