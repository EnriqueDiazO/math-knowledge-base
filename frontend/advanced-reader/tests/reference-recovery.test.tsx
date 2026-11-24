import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { ReferenceForm } from "../src/study/ReferenceForm";
import type { StudyContext } from "../src/study/api";
const context = {library_id:"owned",runtime_id:"runtime",name:"Library",preparation:{state:"ready",version:"1",notes_ready:true,reading_ready:true,reason:""}} as StudyContext;
const proposal = {reference_type:"article",title:"Resultado propuesto",authors:[{family:"Noether",given:"Emmy",orcid:"0000-0000-0000-0001"}],journal:"Revista conservada",publisher:"Editorial conservada",bibtex:{key:"Noether1918",extra:{pages:"235-257"}},provenance:{import_method:"online_lookup",warnings:["Comprobar edición"]},accessed_at:"2026-11-20T12:34:56Z"};
const writes: Record<string,unknown>[] = [];
beforeEach(() => {
 localStorage.clear(); writes.length=0;
 vi.stubGlobal("fetch",vi.fn(async(input, options) => {
  const path=String(input);
  if(path.endsWith("/catalog/preparation"))return Response.json({state:"ready",version:"1",reason:""});
  const body=options?.body ? JSON.parse(String(options.body)) : {};
  if(body.action==="identifier") return Response.json({candidates:[{reference_data:proposal}]});
  if(body.action==="save") { writes.push(body.reference_data); throw new TypeError("Respuesta perdida"); }
  throw new Error("Unexpected request "+path);
 }));
});
afterEach(() => {cleanup();vi.unstubAllGlobals();});
it("recovers the complete reviewed proposal and retries the same reference after reload",async()=>{
 const user=userEvent.setup(), done=vi.fn();
 let app=render(<ReferenceForm context={context} sourceId="source" done={done}/>);
 await user.type(screen.getByLabelText("Consultar DOI o ISBN"),"10.1000/example");
 await user.click(screen.getByRole("button",{name:"Buscar metadatos"}));
 await user.click(await screen.findByRole("button",{name:"Revisar propuesta"}));
 await user.clear(screen.getByLabelText("Título de la referencia"));
 await user.type(screen.getByLabelText("Título de la referencia"),"Corrección manual");
 app.unmount();
 app=render(<ReferenceForm context={context} sourceId="source" done={done}/>);
 expect(screen.getByLabelText("Título de la referencia")).toHaveValue("Corrección manual");
 await user.click(screen.getByRole("button",{name:"Guardar referencia"}));
 await waitFor(()=>expect(writes).toHaveLength(1));
 expect(writes[0]).toMatchObject({...proposal,title:"Corrección manual"});
 await screen.findByText(/No se confirmó la conexión/u);
 app.unmount();
 render(<ReferenceForm context={context} sourceId="source" done={done}/>);
 await user.click(screen.getByRole("button",{name:"Guardar referencia"}));
 await waitFor(()=>expect(writes).toHaveLength(2));
 expect(writes[1]).toEqual(writes[0]);
 expect(done).not.toHaveBeenCalled();
});

it("keeps old manual drafts compatible and uses no invented proposal metadata",async()=>{
 const user=userEvent.setup();
 const key="mathmongo-reference-v1-owned-source";
 const old={reference_id:"ref-old",reference_type:"book",title:"Ficha manual anterior",author:"Ada",year:"1843",doi:"",isbn:"",url:"",accessed_at:""};
 localStorage.setItem(key,JSON.stringify(old));
 render(<ReferenceForm context={context} sourceId="source" done={vi.fn()}/>);
 expect(screen.getByLabelText("Título de la referencia")).toHaveValue(old.title);
 await user.click(screen.getByRole("button",{name:"Guardar referencia"}));
 await waitFor(()=>expect(writes).toHaveLength(1));
 expect(writes[0]).toMatchObject({reference_id:old.reference_id,title:old.title,authors:[{literal:"Ada"}],year:1843,accessed_at:null});
 expect(writes[0]).not.toHaveProperty("journal");
});

it("preserves an unreadable proposal and requires recovery before sending a partial reference",async()=>{
 const user=userEvent.setup();
 const key="mathmongo-reference-v1-owned-source";
 const raw=JSON.stringify({reference_id:"ref-old",reference_type:"book",title:"Contenido a recuperar",author:"Ada",year:"1843",doi:"",isbn:"",url:"",accessed_at:"",proposal_json:"{broken"});
 localStorage.setItem(key,raw);
 render(<ReferenceForm context={context} sourceId="source" done={vi.fn()}/>);
 expect(screen.getByRole("alert").textContent).toContain("El borrador original se conserva");
 expect(screen.getByRole("button",{name:"Guardar referencia"})).toBeDisabled();
 expect(localStorage.getItem(key)).toBe(raw);
 expect(writes).toEqual([]);
 await user.click(screen.getByRole("button",{name:"Reiniciar ficha conservando copia"}));
 expect(screen.getByLabelText("Título de la referencia")).toHaveValue("");
 const archive=Object.keys(localStorage).find(name=>name.startsWith(key+"-archive-"))!;
 expect(localStorage.getItem(archive)).toBe(raw);
});
