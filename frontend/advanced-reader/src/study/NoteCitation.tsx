/** A citation chooses an existing canonical reference; it never rewrites its metadata. */
import { emptyLocator } from "../knowledge-map/bibliography";
import type { StudyDraft } from "./drafts";
import type { SourceDetail, StudyContext } from "./api";
import { useStudyResource } from "./navigation";

export function NoteCitation({context,draft,changed,disabled}:{context:StudyContext;draft:StudyDraft;changed:(patch:Partial<StudyDraft>)=>void;disabled:boolean}) {
  const source=useStudyResource<SourceDetail>(context,draft.source?"/sources/"+encodeURIComponent(draft.source):"/context");
  return <details><summary>Referencia y localizador</summary>
    <fieldset disabled={disabled}>
      <label>Referencia bibliográfica<select value={draft.referenceId||""} onChange={e=>changed({referenceId:e.target.value||undefined})}>
        <option value="" disabled={!!draft.noteId&&!!draft.referenceId}>Sin nueva referencia</option>
        {draft.referenceId&&!source.data?.references?.some(r=>r.reference_id===draft.referenceId)&&<option value={draft.referenceId}>Referencia conservada</option>}
        {source.data?.references?.map(r=><option key={r.reference_id} value={r.reference_id}>{r.title}</option>)}
      </select></label>
      {([['printed_page','Página impresa'],['chapter','Capítulo'],['section','Sección'],['theorem','Teorema'],['passage','Pasaje citado']] as const).map(([key,label])=><label key={key}>{label}<input value={draft.referenceLocator?.[key]||""} onChange={e=>changed({referenceLocator:{...emptyLocator(),...draft.referenceLocator,[key]:e.target.value}})}/></label>)}
    </fieldset>
    {source.error&&<p role="alert">No pudimos consultar las referencias. La cita existente se conserva. <button type="button" onClick={source.retry}>Reintentar referencias</button></p>}
  </details>;
}
