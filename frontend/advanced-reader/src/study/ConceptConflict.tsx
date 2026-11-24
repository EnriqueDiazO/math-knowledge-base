/** Reviewing a conflict does not save, discard or silently replace a local draft. */
import { useState } from "react";
import type { StudyContext, ConceptDetail } from "./api";
import { studyRequest } from "./api";
import { DocumentContent } from "./DocumentSurface";
import { useOperationScope } from "./useOperationScope";
export function ConceptConflict({
  context,
  identity,
  adopt,
}: {
  context: StudyContext;
  identity: string;
  adopt: (remote: ConceptDetail) => void;
}) {
  const scope = useOperationScope(context),
    [remote, setRemote] = useState<ConceptDetail>(),
    [message, setMessage] = useState(""),
    [busy, setBusy] = useState(false);
  const review = async () => {
    setBusy(true);
    setMessage("Consultando la versión guardada…");
    try {
      const value = await studyRequest<ConceptDetail>(
        "/concepts/detail?" + new URLSearchParams({ key: identity }),
        context,
      );
      if (!scope.active) return;
      setRemote(value);
      setMessage("Versión guardada consultada. Tu borrador sigue intacto.");
    } catch (error) {
      if (scope.active) setMessage((error as Error).message);
    } finally {
      if (scope.active) setBusy(false);
    }
  };
  return (
    <aside className="study-conflict">
      <p>
        Otra ventana cambió el concepto. Conservamos tu borrador; consulta esa
        versión antes de combinar los cambios.
      </p>
      <button type="button" disabled={busy} onClick={() => void review()}>
        Consultar versión guardada
      </button>
      {message && <p role="status">{message}</p>}
      {remote && (
        <>
          <h2>Versión guardada: {remote.titulo}</h2>
          <DocumentContent content={remote.contenido_latex} context={context} />
          <p>
            Se conservará una copia local de tu borrador. Tus campos editados se
            mantienen y los que no cambiaste adoptan la versión consultada.
            Revisa el resultado y guarda deliberadamente.
          </p>
          <button type="button" onClick={() => adopt(remote)}>
            Combinar mi borrador sobre esta revisión
          </button>
        </>
      )}
    </aside>
  );
}
