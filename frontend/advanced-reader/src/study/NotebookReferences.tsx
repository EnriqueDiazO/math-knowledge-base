/** Bibliography uses existing source/reference pickers and note-local snapshots. */
import { useState } from "react";
import { SourcePicker } from "./SourcePicker";
import { ReferencePicker } from "./ReferencePicker";
import type { StudyContext } from "./api";
import type { DiaryDetail } from "./notebook-state";

export function NotebookReferences({
  context,
  selected,
  existing,
  changed,
}: {
  context: StudyContext;
  selected: string[];
  existing: DiaryDetail["references"];
  changed: (ids: string[]) => void;
}) {
  const [source, setSource] = useState(""),
    [reference, setReference] = useState("");
  return (
    <details>
      <summary>Referencias de la entrada</summary>
      <p>
        Las referencias guardan una copia bibliográfica propia. Editar el
        catálogo no reescribe las citas de esta entrada.
      </p>
      <ul>
        {existing
          .filter((item) => !item.catalog_reference_id)
          .map((item) => (
            <li key={item.reference_id}>
              {item.title} · referencia histórica conservada
            </li>
          ))}
        {selected.map((id) => (
          <li key={id}>
            {existing.find((item) => item.catalog_reference_id === id)?.title ||
              "Referencia seleccionada"}
            <button
              type="button"
              onClick={() => changed(selected.filter((item) => item !== id))}
            >
              Retirar referencia de esta entrada
            </button>
          </li>
        ))}
      </ul>
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
        disabled={!reference || selected.includes(reference)}
        onClick={() => {
          changed([...selected, reference]);
          setReference("");
        }}
      >
        Vincular referencia a la entrada
      </button>
    </details>
  );
}
