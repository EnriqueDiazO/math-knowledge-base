/** Bibliographic insertion is deliberate, editable LaTeX from the existing catalog. */
import { useState } from "react";
import { SourcePicker } from "./SourcePicker";
import { ReferencePicker } from "./ReferencePicker";
import { studyRequest, type StudyContext } from "./api";
import { useOperationScope } from "./useOperationScope";
import type { Family } from "./structured-state";
export function StructuredReferences({
  context,
  family,
  insert,
}: {
  context: StudyContext;
  family: Family;
  insert: (latex: string) => boolean;
}) {
  const [source, setSource] = useState(""),
    [reference, setReference] = useState(""),
    [message, setMessage] = useState(""),
    [busy, setBusy] = useState(false),
    scope = useOperationScope(context);
  return (
    <details>
      <summary>Insertar referencia bibliográfica</summary>
      <p>
        La cita se incorpora a la región seleccionada como LaTeX editable. El
        catálogo compartido se conserva.
      </p>
      <fieldset disabled={busy}>
        <SourcePicker
          context={context}
          value={source}
          choose={(id) => {
            setSource(id);
            setReference("");
          }}
        />
        {source && (
          <ReferencePicker
            key={source}
            context={context}
            sourceId={source}
            value={reference}
            changed={setReference}
          />
        )}
        <button
          type="button"
          disabled={!reference || busy}
          onClick={async () => {
            setBusy(true);
            setMessage("Recuperando la cita para esta región…");
            try {
              const result = await studyRequest<{ latex: string }>(
                "/structured/" +
                  family +
                  "/references/" +
                  encodeURIComponent(reference),
                context,
              );
              if (scope.active) {
                const inserted = insert(result.latex);
                setMessage(
                  inserted
                    ? "Cita incorporada al borrador; guarda para conservarla en la biblioteca."
                    : "No se incorporó la cita. Completa la fórmula de esta región y vuelve a intentarlo; el borrador se conserva.",
                );
              }
            } catch (error) {
              if (scope.active) setMessage((error as Error).message);
            } finally {
              if (scope.active) setBusy(false);
            }
          }}
        >
          Insertar cita en esta región
        </button>
      </fieldset>
      <p role="status">{message}</p>
    </details>
  );
}
