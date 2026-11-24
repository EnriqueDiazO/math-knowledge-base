import { useState } from "react";
import { studyRequest } from "./api";
import type { StudyContext } from "./api";
import { useLocalForm } from "./useLocalForm";
import { useOperationScope } from "./useOperationScope";
import { AuthoringPreparation } from "./AuthoringPreparation";
import {
  restoredProposal,
  referenceAccessDate,
  type ReferenceData,
  type ReferenceDraft,
} from "./reference-draft";

const referenceTypes = {
  book: "Libro",
  article: "Artículo",
  chapter: "Capítulo",
  thesis: "Tesis",
  web: "Página web",
  report: "Informe",
  proceedings: "Actas",
  course: "Curso",
  misc: "Otro documento",
};

type CaptureResult = {
  status: string;
  message?: string;
  reference_data?: ReferenceData;
  candidates?: { reference_data: ReferenceData; existing?: boolean }[];
};
export function ReferenceForm({
  context,
  sourceId,
  done,
}: {
  context: StudyContext;
  sourceId: string;
  done: () => void;
}) {
  const scope = useOperationScope(context);
  const draft = useLocalForm<ReferenceDraft>(
    "mathmongo-reference-v1-" + context.library_id + "-" + sourceId,
    () => ({
      reference_id: "ref_" + crypto.randomUUID(),
      reference_type: "book",
      title: "",
      author: "",
      year: "",
      doi: "",
      isbn: "",
      url: "",
      accessed_at: "",
    }),
  );
  const [query, setQuery] = useState(""),
    [message, setMessage] = useState(""),
    [proposals, setProposals] = useState<
      NonNullable<CaptureResult["candidates"]>
    >([]),
    [sending, setSending] = useState(false);
  const values = draft.state;
  const { data: proposal, error: proposalError } = restoredProposal(
    values.proposal_json,
  );
  const capture = async (existing?: string) => {
    if (sending || proposalError) return;
    setSending(true);
    try {
      const reference_data = {
        ...proposal,
        reference_id: values.reference_id,
        reference_type: values.reference_type,
        title: values.title,
        authors:
          values.author ===
          (proposal.authors ?? [])
            .map(
              (a) => a.literal || [a.given, a.family].filter(Boolean).join(" "),
            )
            .join("; ")
            ? (proposal.authors ?? [])
            : values.author
                .split(";")
                .map((name) => name.trim())
                .filter(Boolean)
                .map((literal) => ({ literal })),
        year: values.year ? Number(values.year) : null,
        doi: values.doi || null,
        isbn: values.isbn ? values.isbn.split(",").map((x) => x.trim()) : [],
        url: values.url || null,
        accessed_at: referenceAccessDate(values.accessed_at, proposal.accessed_at),
      };
      if (!draft.set(values)) return;
      const result = await studyRequest<CaptureResult>(
        "/bibliography",
        context,
        {
          request_id: crypto.randomUUID(),
          action: "save",
          source_id: sourceId,
          ...(existing
            ? { existing_reference_id: existing }
            : { reference_data }),
        },
      );
      if (!scope.active) return;
      if (result.status === "saved") {
        draft.clear();
        done();
      } else {
        setMessage(
          result.message || "No se confirmó la referencia. Revisa los datos.",
        );
        setProposals(result.candidates ?? []);
      }
    } catch (error) {
      if (!scope.active) return;
      setMessage((error as Error).message);
    } finally {
      if (scope.active) setSending(false);
    }
  };
  const lookup = async (local = false) => {
    if (sending || proposalError) return;
    setSending(true);
    try {
      const result = await studyRequest<CaptureResult>(
        "/bibliography",
        context,
        { request_id: crypto.randomUUID(), action: local ? "local" : "identifier", query },
      );
      if (!scope.active) return;
      setProposals(result.candidates ?? []);
      setMessage(
        result.message ||
          "Revisa la propuesta antes de guardar. También puedes completar la ficha manualmente.",
      );
    } catch (error) {
      if (!scope.active) return;
      setMessage((error as Error).message);
    } finally {
      if (scope.active) setSending(false);
    }
  };
  const choose = (data: ReferenceData) => {
    draft.set({
      ...values,
      proposal_json: JSON.stringify(data),
      accessed_at: data.accessed_at?.slice(0, 10) || "",
      reference_type: data.reference_type || "misc",
      title: data.title || "",
      author: (data.authors ?? [])
        .map((a) => a.literal || [a.given, a.family].filter(Boolean).join(" "))
        .join("; "),
      year: data.year ? String(data.year) : "",
      doi: data.doi || "",
      isbn: (data.isbn ?? []).join(", "),
      url: data.url || "",
    });
  };
  return (
    <section>
      <h2>Añadir referencia</h2>
      <p>
        La captura manual funciona sin Internet. DOI e ISBN son opcionales
        cuando no correspondan al documento.
      </p>
      <AuthoringPreparation context={context} />
      <label>
        Consultar DOI o ISBN
        <input
          value={query}
          onChange={(event) => setQuery(event.target.value)}
        />
      </label>
      <button
        type="button"
        disabled={sending || !!proposalError || !query.trim()}
        onClick={() => void lookup()}
      >
        Buscar metadatos
      </button>
      <button type="button" disabled={sending || !!proposalError || !query.trim()} onClick={() => void lookup(true)}>Buscar en mis referencias</button>
      {proposals.map((item, index) => (
        <article key={index}>
          <h3>{item.reference_data.title || "Propuesta bibliográfica"}</h3>
          <button type="button" onClick={() => choose(item.reference_data)}>
            Revisar propuesta
          </button>
          {item.existing && (
            <button
              type="button"
              onClick={() => void capture(item.reference_data.reference_id)}
            >
              Usar referencia existente
            </button>
          )}
        </article>
      ))}
      {proposalError && (
        <aside role="alert">
          <p>{proposalError}</p>
          <button type="button" onClick={draft.download}>
            Descargar borrador de referencia
          </button>
          <button type="button" onClick={draft.restart}>
            Reiniciar ficha conservando copia
          </button>
        </aside>
      )}
      <form
        onSubmit={(event) => {
          event.preventDefault();
          void capture();
        }}
      >
        <fieldset disabled={sending}>
          <label>
            Tipo de referencia
            <select
              value={values.reference_type}
              onChange={(event) =>
                draft.set({ ...values, reference_type: event.target.value })
              }
            >
              {Object.entries(referenceTypes).map(([value, label]) => (
                <option key={value} value={value}>
                  {label}
                </option>
              ))}
            </select>
          </label>
          {(
            [
              ["title", "Título de la referencia"],
              ["author", "Autor u organización"],
              ["year", "Año de publicación"],
              ["doi", "DOI"],
              ["isbn", "ISBN separados por comas"],
              ["url", "URL"],
              ["accessed_at", "Fecha de consulta"],
            ] as const
          ).map(([key, label]) => (
            <label key={key}>
              {label}
              <input
                type={
                  key === "accessed_at"
                    ? "date"
                    : key === "year"
                      ? "number"
                      : "text"
                }
                required={key === "title"}
                value={values[key]}
                onChange={(event) =>
                  draft.set({ ...values, [key]: event.target.value })
                }
              />
            </label>
          ))}
        </fieldset>
        {(message || draft.problem) && (
          <p role="status">{message || draft.problem}</p>
        )}
        <button type="submit" disabled={sending || !!proposalError} className="primary-button">
          Guardar referencia
        </button>
      </form>
    </section>
  );
}
