/** Paged source selection; the chosen identity survives searches and later pages. */
import { useState } from "react";
import type { Page, SourceSummary, StudyContext } from "./api";
import { useStudyResource } from "./navigation";

export function SourcePicker({context,value,selectedName,choose,allowAll=false}:{context:StudyContext;value:string;selectedName?:string;choose:(id:string)=>void;allowAll?:boolean}) {
  const [query,setQuery]=useState(""),[page,setPage]=useState(1);
  const sources=useStudyResource<Page<SourceSummary>>(context,"/library?"+new URLSearchParams({q:query,page:String(page)}));
  return <div className="study-source-picker">
    <label>Buscar fuente<input type="search" value={query} onChange={e=>{setQuery(e.target.value);setPage(1);}}/></label>
    <label>{allowAll?"Filtrar por fuente":"Fuente administrada"}<select value={value} onChange={e=>choose(e.target.value)}>
      <option value="">{allowAll?"Todas las fuentes":"Selecciona una fuente"}</option>
      {value&&!sources.data?.items.some(s=>s.source_id===value)&&<option value={value}>{selectedName||"Fuente seleccionada"}</option>}
      {sources.data?.items.map(source=><option key={source.source_id} value={source.source_id}>{source.name}</option>)}
    </select></label>
    {sources.error&&<p role="alert">{sources.error}<button type="button" onClick={sources.retry}>Reintentar fuentes</button></p>}
    {(sources.data?.total??0)>20&&<nav aria-label="Páginas de fuentes">
      <button type="button" disabled={page===1} onClick={()=>setPage(page-1)}>Fuentes anteriores</button>
      <span>Página {page}</span>
      <button type="button" disabled={page*20>=(sources.data?.total??0)} onClick={()=>setPage(page+1)}>Más fuentes</button>
    </nav>}
  </div>;
}
