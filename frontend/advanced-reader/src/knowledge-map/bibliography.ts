/** One canonical reference picker; network/database actions go through the backend. */
import { element, button, field, selector } from "./ui";
export type ReferenceData = {
  reference_id: string;
  source_ids?: string[];
  reference_type?: string;
  title?: string | null;
  authors?: {
    literal?: string | null;
    given?: string | null;
    family?: string | null;
    orcid?: string | null;
  }[];
  year?: number | null;
  year_raw?: string | null;
  journal?: string | null;
  publisher?: string | null;
  volume?: string | null;
  number?: string | null;
  edition?: string | null;
  language?: string | null;
  isbn?: string[];
  doi?: string | null;
  url?: string | null;
  bibtex?: {
    key?: string | null;
    entry_type?: string | null;
    extra?: Record<string, string>;
  };
  provenance?: {
    warnings?: string[];
    external_lookup?: {
      provider: string;
      record_kind: string;
      retrieved_at: string;
    };
  };
};
export type CitationLocator = {
  printed_page: string;
  pdf_page: number | null;
  chapter: string;
  section: string;
  theorem: string;
  passage: string;
};
export const emptyLocator = (): CitationLocator => ({
  printed_page: "",
  pdf_page: null,
  chapter: "",
  section: "",
  theorem: "",
  passage: "",
});
type Candidate = {
  reference_data: ReferenceData;
  edition_ids?: string[];
  existing?: boolean;
  match?: string;
};
export type BibliographyResult = {
  request_id?: string;
  status: string;
  candidates?: Candidate[];
  reference_data?: ReferenceData;
  providers?: string[];
  query?: string;
  retry_after?: number;
  message?: string;
};
export type BibliographyDraft = {
  open: boolean;
  query: string;
  title: string;
  author: string;
  pending?: string;
  status: string;
  candidates: Candidate[];
  selected?: Candidate;
};
const messages: Record<string, string> = {
  idle: "Busca en tu biblioteca, pega un identificador o prepara una ficha manual.",
  searching: "Buscando referencia…",
  found: "Ficha recuperada. Revisa los campos antes de guardar.",
  partial: "Resultado parcial: puedes completar los datos ausentes.",
  candidates:
    "Selecciona un candidato. Una obra necesita una edición para asignarle ISBN y fecha.",
  duplicates:
    "Hay coincidencias locales. Puedes usar una ficha existente; no se fusionaron registros.",
  not_found:
    "No se pudo recuperar la referencia. Puedes usar captura manual; esto no demuestra que el identificador no exista.",
  invalid:
    "Revisa el identificador, el dígito de control del ISBN y los campos de la ficha.",
  unavailable:
    "Proveedor o catálogo no disponible. La consulta, las correcciones y el documento se conservan.",
  rate_limited:
    "El proveedor limita las consultas. Espera antes de reintentar.",
  conflict:
    "La referencia cambió. Revisa la ficha existente; las correcciones locales se conservan.",
  saved:
    "Ficha guardada y seleccionada para esta cita. Guarda el documento para confirmar el enlace.",
};
export function consumeBibliography(
  state: BibliographyDraft,
  result?: BibliographyResult,
): ReferenceData | undefined {
  if (!state.pending || result?.request_id !== state.pending) return;
  state.pending = undefined;
  state.status = result.status;
  if (result.candidates?.length)
    state.candidates = structuredClone(result.candidates);
  if (result.status === "saved" && result.reference_data) {
    state.open = false;
    return structuredClone(result.reference_data);
  }
}
export function referenceLabel(reference: ReferenceData): string {
  const names = (reference.authors ?? [])
    .map((a) => a.literal || [a.given, a.family].filter(Boolean).join(" "))
    .join("; ");
  return [names, reference.title || "Sin título", reference.year]
    .filter((v) => v !== null && v !== undefined && v !== "")
    .join(" · ");
}
export function renderBibliography(
  parent: HTMLElement,
  state: BibliographyDraft,
  send: (payload: Record<string, unknown>) => void,
  source: string,
  changed: () => void,
  close: () => void,
): () => void {
  const dialog = element("dialog", "", "document-dialog bibliography-dialog");
  dialog.setAttribute("aria-label", "Referencias del documento");
  const render = () => {
    dialog.replaceChildren();
    const header = element("header", "", "document-header");
    header.append(element("h2", "Referencia bibliográfica"));
    button(
      "Volver al documento",
      () => {
        state.open = false;
        changed();
        close();
      },
      header,
    );
    dialog.append(
      header,
      element(
        "p",
        "Se envía sólo el identificador o título/autor a los catálogos públicos. No se suben notas ni PDF. La ficha, el pasaje citado y el PDF son recursos distintos.",
      ),
    );
    const request = (action: string, payload: Record<string, unknown>) => {
      const id = crypto.randomUUID();
      state.pending = id;
      state.status = "searching";
      changed();
      send({ request_id: id, action, ...payload });
      render();
    };
    field(dialog, "Pegar DOI o ISBN", state.query, (value) => {
      state.query = value;
      changed();
    });
    const controls = element("div", "", "bibliography-actions");
    button(
      "Buscar referencia",
      () => request("identifier", { query: state.query }),
      controls,
      true,
    );
    button(
      "Buscar en mi biblioteca",
      () => request("local", { query: state.query }),
      controls,
    );
    button(
      "Ficha manual",
      () => {
        state.selected = {
          reference_data: {
            reference_id: "ref_" + crypto.randomUUID(),
            reference_type: "book",
            authors: [],
            title: "",
          },
        };
        changed();
        render();
      },
      controls,
    );
    dialog.append(controls);
    const search = element("details");
    search.append(element("summary", "Buscar libros por título y autor"));
    field(search, "Título del libro", state.title, (value) => {
      state.title = value;
      changed();
    });
    field(search, "Autor del libro", state.author, (value) => {
      state.author = value;
      changed();
    });
    button(
      "Buscar libros",
      () => request("title", { query: state.title, author: state.author }),
      search,
    );
    dialog.append(search);
    const status = element("p", messages[state.status] ?? state.status);
    status.setAttribute("role", "status");
    dialog.append(status);
    state.candidates.forEach((candidate) => {
      const card = element("section", "", "reference-candidate");
      card.append(element("p", referenceLabel(candidate.reference_data)));
      button(
        candidate.existing
          ? "Usar referencia existente"
          : "Revisar esta propuesta",
        () => {
          state.selected = structuredClone(candidate);
          changed();
          render();
        },
        card,
      );
      candidate.edition_ids?.forEach((edition) =>
        button(
          "Consultar edición " + edition,
          () => request("edition", { query: edition }),
          card,
        ),
      );
      dialog.append(card);
    });
    const selected = state.selected;
    if (!selected) return;
    const ref = selected.reference_data;
    const metadata = element("section", "", "reference-proposal");
    metadata.append(
      element(
        "h3",
        selected.existing
          ? "Ficha local: se conserva sin sobrescribir"
          : "Propuesta editable",
      ),
    );
    if (selected.existing) {
      metadata.append(
        element("p", referenceLabel(ref)),
        element(
          "p",
          "Para corregir una ficha compartida usa Edit Source, donde puedes revisar las diferencias.",
        ),
      );
    } else {
      selector(
        metadata,
        "Tipo de documento",
        [
          "book",
          "article",
          "chapter",
          "thesis",
          "proceedings",
          "report",
          "web",
          "misc",
          "other",
        ].map((value) => ({ value, text: value })),
        ref.reference_type ?? "book",
        (value) => {
          ref.reference_type = value;
          changed();
        },
      );
      field(metadata, "Título de la referencia", ref.title ?? "", (value) => {
        ref.title = value || null;
        changed();
      });
      field(
        metadata,
        "Autores (uno por línea; apellido | nombre o nombre literal)",
        (ref.authors ?? [])
          .map((a) => a.literal || `${a.family ?? ""} | ${a.given ?? ""}`)
          .join("\n"),
        (value) => {
          ref.authors = value
            .split("\n")
            .filter((s) => s.trim())
            .map((s) =>
              s.includes("|")
                ? {
                    family: s.split("|")[0].trim(),
                    given: s.split("|").slice(1).join("|").trim(),
                  }
                : { literal: s.trim() },
            );
          changed();
        },
        true,
      );
      field(
        metadata,
        "Año de la edición/publicación",
        ref.year === null || ref.year === undefined ? "" : String(ref.year),
        (value) => {
          ref.year = value.trim() ? Number(value) : null;
          changed();
        },
      );
      const details = element("details");
      details.append(
        element("summary", "Contenedor, edición, roles e identificadores"),
      );
      const scalar: [keyof ReferenceData, string][] = [
        ["year_raw", "Fecha declarada"],
        ["journal", "Revista"],
        ["publisher", "Editorial"],
        ["edition", "Edición"],
        ["volume", "Volumen"],
        ["number", "Número"],
        ["language", "Idioma"],
        ["doi", "DOI"],
        ["url", "URL"],
      ];
      scalar.forEach(([key, label]) =>
        field(details, label, String(ref[key] ?? ""), (value) => {
          Object.assign(ref, { [key]: value || null });
          changed();
        }),
      );
      field(
        details,
        "ISBN de esta edición",
        (ref.isbn ?? []).join("\n"),
        (value) => {
          ref.isbn = value
            .split(/[\n;,]/u)
            .map((s) => s.trim())
            .filter(Boolean);
          changed();
        },
        true,
      );
      const extra = (ref.bibtex ??= {});
      extra.extra ??= {};
      (
        [
          ["booktitle", "Libro contenedor"],
          ["pages", "Páginas de la publicación"],
          ["pagination", "Paginación de la edición"],
          ["editor", "Editores"],
          ["translator", "Traductores"],
          ["contributions", "Otros roles declarados"],
        ] as const
      ).forEach(([key, label]) =>
        field(details, label, extra.extra![key] ?? "", (value) => {
          if (value) extra.extra![key] = value;
          else delete extra.extra![key];
          changed();
        }),
      );
      metadata.append(details);
    }
    ref.provenance?.warnings?.forEach((warning) =>
      metadata.append(element("p", warning)),
    );
    const provenance = ref.provenance?.external_lookup;
    if (provenance)
      metadata.append(
        element(
          "p",
          `${provenance.provider} · ${provenance.record_kind} · ${provenance.retrieved_at}`,
        ),
      );
    button(
      "Guardar ficha y citar",
      () =>
        request("save", {
          source_id: source,
          ...(selected.existing
            ? { existing_reference_id: ref.reference_id }
            : { reference_data: ref }),
        }),
      metadata,
      true,
    ).disabled = !!state.pending || !source;
    if (!source)
      metadata.append(
        element(
          "p",
          "Elige primero una Source administrada para este documento.",
        ),
      );
    dialog.append(metadata);
  };
  dialog.addEventListener("cancel", (event) => {
    event.preventDefault();
    state.open = false;
    changed();
    close();
  });
  render();
  parent.append(dialog);
  dialog.showModal();
  return () => {
    dialog.close();
    dialog.remove();
  };
}
