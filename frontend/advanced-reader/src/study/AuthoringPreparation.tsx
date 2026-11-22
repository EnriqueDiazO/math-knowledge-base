import { useState } from "react";
import { studyRequest } from "./api";
import type { StudyContext } from "./api";
import { useStudyResource } from "./navigation";

type State = {
  state: "ready" | "pending" | "incompatible" | "unverified";
  version: string;
  reason: string;
};
export function AuthoringPreparation({ context }: { context: StudyContext }) {
  const resource = useStudyResource<State>(context, "/catalog/preparation");
  const [message, setMessage] = useState(""),
    [sending, setSending] = useState(false);
  const prepare = async () => {
    if (!resource.data) return;
    setSending(true);
    try {
      const state = await studyRequest<State>("/catalog/prepare", context, {
        version: resource.data.version,
      });
      setMessage(
        state.state === "ready"
          ? "Biblioteca preparada. Aún no se ha guardado esta ficha."
          : state.reason,
      );
      resource.retry();
    } catch (error) {
      setMessage((error as Error).message);
    } finally {
      setSending(false);
    }
  };
  if (resource.data?.state === "ready" && !message) return null;
  return (
    <aside className="study-preparation">
      <p>
        {resource.error ||
          resource.data?.reason ||
          "Comprobando las funciones de creación…"}
      </p>
      {resource.data?.state === "pending" && (
        <>
          <p>
            Se crearán únicamente los índices compatibles que faltan para
            fuentes y conceptos. No se borran, fusionan ni migran documentos.
          </p>
          <button
            type="button"
            disabled={sending}
            onClick={() => void prepare()}
          >
            {sending ? "Preparando…" : "Preparar biblioteca"}
          </button>
        </>
      )}
      <button type="button" onClick={resource.retry}>
        Volver a comprobar
      </button>
      {message && <p role="status">{message}</p>}
    </aside>
  );
}
