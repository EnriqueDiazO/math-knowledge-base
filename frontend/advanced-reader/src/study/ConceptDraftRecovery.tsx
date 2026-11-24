/** Read-only discovery keeps drafts recoverable after the original window closes. */
import { useState } from "react";
import { discoverConceptDrafts } from "./concept-draft-discovery";
import type { Draft } from "../knowledge-map/model";
import { downloadDocument } from "./api";

export function ConceptDraftRecovery({
  library,
  current,
  id,
  locked,
  recover,
}: {
  library: string;
  current: string;
  id: string;
  locked: boolean;
  recover: (draft: Draft) => void;
}) {
  const [result, setResult] =
    useState<ReturnType<typeof discoverConceptDrafts>>();
  return (
    <details className="study-draft-recovery">
      <summary>Recuperar borradores de otras ventanas</summary>
      <p>
        Busca copias locales de este documento en esta biblioteca. Recuperar una
        copia no la guarda en la biblioteca ni modifica el archivo original.
      </p>
      <button
        type="button"
        onClick={() => setResult(discoverConceptDrafts(library, current, id))}
      >
        Buscar borradores locales
      </button>
      {result?.unavailable && (
        <p role="alert">
          No pudimos leer algunos borradores. Se conservan sus archivos; permite
          el almacenamiento del navegador y vuelve a buscar.
        </p>
      )}
      {result && !result.copies.length && (
        <p role="status">
          No encontramos otras copias recuperables de este documento.
        </p>
      )}
      {result?.copies.map(({ archive, draft }) => (
        <article key={archive}>
          <h3>{draft.title || "Sin título"}</h3>
          <p>
            {draft.updated
              ? new Date(draft.updated).toLocaleString("es-MX")
              : "Fecha desconocida"}{" "}
            · {draft.content.length} caracteres
          </p>
          <button
            type="button"
            disabled={locked}
            onClick={() => recover(draft)}
          >
            Recuperar una copia
          </button>
          <button
            type="button"
            onClick={() =>
              downloadDocument(
                new Blob([JSON.stringify(draft, null, 2)], {
                  type: "application/json",
                }),
                "mathmongo-borrador-recuperado.json",
              )
            }
          >
            Descargar esta copia
          </button>
        </article>
      ))}
    </details>
  );
}
