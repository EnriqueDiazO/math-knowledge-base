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
  insert: (latex: string) => void;
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
          try {
            const result = await studyRequest<{ latex: string }>(
              "/structured/" +
                family +
                "/references/" +
                encodeURIComponent(reference),
              context,
            );
            if (scope.active) {
              insert(result.latex);
              setMessage(
                "Cita incorporada al borrador; guarda para conservarla en la biblioteca.",
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
      <p role="status">{message}</p>
    </details>
  );
}
