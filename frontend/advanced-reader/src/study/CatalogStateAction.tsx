/** Context-bound archive/reactivate controls; never remove stored records or bytes. */
import { useState } from "react";
import { studyRequest, type StudyContext } from "./api";
import { useOperationScope } from "./useOperationScope";
export function CatalogStateAction({
  context,
  path,
  revision,
  status,
  kind,
  done,
  pending,
}: {
  context: StudyContext;
  path: string;
  revision: string;
  status: string;
  kind: "fuente" | "documento";
  done: () => void;
  pending?: (busy: boolean) => void;
}) {
  const scope = useOperationScope(context),
    [confirmed, setConfirmed] = useState(false),
    [busy, setBusy] = useState(false),
    [message, setMessage] = useState("");
  const target = status === "archived" ? "active" : "archived",
    verb = target === "archived" ? "Archivar" : "Reactivar";
  const run = async () => {
    if (!confirmed || busy) return;
    setBusy(true);
    pending?.(true);
    try {
      const record = await studyRequest<{ status: string }>(
        path + "/state",
        context,
        { revision, status: target },
      );
      if (!scope.active) return;
      if (record.status !== target)
        throw new Error(
          "No se confirmó el estado. Actualiza la ficha antes de reintentar.",
        );
      setConfirmed(false);
      done();
    } catch (error) {
      if (scope.active) setMessage((error as Error).message);
    } finally {
      pending?.(false);
      if (scope.active) setBusy(false);
    }
  };
  return (
    <details>
      <summary>Organizar {kind}</summary>
      <p>
        {target === "archived"
          ? "Se ocultará de la lista activa. Se conservarán sus archivos, referencias, notas y conceptos; podrás reactivarlo."
          : "Volverá a aparecer en la lista activa. No se duplicará ni se reemplazará su contenido."}
      </p>
      <label>
        <input
          type="checkbox"
          checked={confirmed}
          onChange={(event) => setConfirmed(event.target.checked)}
        />
        Confirmar {verb.toLowerCase()} {kind}
      </label>
      <button
        type="button"
        disabled={!confirmed || busy}
        onClick={() => void run()}
      >
        {verb} {kind}
      </button>
      <p role="status">{message}</p>
    </details>
  );
}
