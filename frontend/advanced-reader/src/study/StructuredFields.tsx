/** Presentation of academic metadata/page choices; persistence stays in the workspace. */
import type { StudyContext } from "./api";
import { StructuredReferences } from "./StructuredReferences";
import {
  regions,
  type Family,
  type Metadata,
  type Region,
  type StructuredDocument,
  type structuredValues,
} from "./structured-state";
export function StructuredFields({
  context,
  family,
  values,
  page,
  region,
  locked,
  remove,
  setRemove,
  metadata,
  changePages,
  select,
  document,
  citation,
}: {
  context: StudyContext;
  family: Family;
  values: ReturnType<typeof structuredValues>;
  page: number;
  region: string;
  locked: boolean;
  remove: boolean;
  setRemove: (value: boolean) => void;
  metadata: (key: keyof Metadata, value: string | string[]) => void;
  changePages: (
    operation: "add" | "duplicate" | "up" | "down" | "remove",
  ) => void;
  select: (index: number, key: string) => void;
  document: (value: StructuredDocument) => void;
  citation: (latex: string) => void;
}) {
  const classic =
    family === "cornell"
      ? "historical_cornell_math_letter_v1"
      : "cpi_landscape_letter_v1";
  return (
    <fieldset disabled={locked}>
      <label>
        Título de la nota
        <input
          value={values.metadata.title || ""}
          onChange={(event) => metadata("title", event.target.value)}
        />
      </label>
      <details>
        <summary>Fecha, proyecto y etiquetas</summary>
        <label>
          Fecha de la nota
          <input
            type="date"
            value={values.metadata.date || ""}
            onChange={(event) => metadata("date", event.target.value)}
          />
        </label>
        <label>
          Proyecto
          <input
            value={values.metadata.project || ""}
            onChange={(event) => metadata("project", event.target.value)}
          />
        </label>
        <label>
          Contexto
          <input
            value={values.metadata.context || ""}
            onChange={(event) => metadata("context", event.target.value)}
          />
        </label>
        <label>
          Etiquetas (una por línea)
          <textarea
            value={values.metadata.tags?.join("\n") || ""}
            onChange={(event) =>
              metadata("tags", event.target.value.split("\n").filter(Boolean))
            }
          />
        </label>
        <label>
          Plantilla de la nota
          <select
            aria-label="Plantilla de la nota"
            value={values.document.template_id}
            onChange={(event) =>
              document({ ...values.document, template_id: event.target.value })
            }
          >
            <option value={classic}>Clásica</option>
            <option value={family + "_hybrid_compact_v1"}>
              Híbrida continua
            </option>
            {![classic, family + "_hybrid_compact_v1"].includes(
              values.document.template_id,
            ) && (
              <option value={values.document.template_id}>
                Plantilla histórica conservada
              </option>
            )}
          </select>
        </label>
      </details>
      <nav aria-label="Páginas de la nota">
        {values.document.pages.map((_, index) => (
          <button
            type="button"
            key={values.keys[index]}
            aria-current={page === index ? "page" : undefined}
            onClick={() => select(index, region)}
          >
            Página {index + 1}
          </button>
        ))}
      </nav>
      <div className="study-actions">
        <button
          type="button"
          disabled={values.document.pages.length >= 30}
          onClick={() => changePages("add")}
        >
          Añadir página
        </button>
        <button
          type="button"
          disabled={values.document.pages.length >= 30}
          onClick={() => changePages("duplicate")}
        >
          Duplicar página
        </button>
        <button
          type="button"
          disabled={page === 0}
          onClick={() => changePages("up")}
        >
          Mover página antes
        </button>
        <button
          type="button"
          disabled={page === values.document.pages.length - 1}
          onClick={() => changePages("down")}
        >
          Mover página después
        </button>
        <button
          type="button"
          disabled={values.document.pages.length === 1}
          onClick={() => setRemove(true)}
        >
          Retirar página
        </button>
      </div>
      {remove && (
        <p>
          Se retirará la página {page + 1} de este borrador. Los archivos
          compartidos se conservan.
          <button type="button" onClick={() => changePages("remove")}>
            Confirmar retirada de esta página
          </button>
          <button type="button" onClick={() => setRemove(false)}>
            Conservar página
          </button>
        </p>
      )}
      <nav aria-label="Regiones de la página">
        {regions[family].map(([key, label]) => (
          <button
            type="button"
            key={key}
            aria-pressed={key === region}
            onClick={() => select(page, key)}
          >
            {label}
          </button>
        ))}
      </nav>
      <label>
        Título de la región
        <input
          value={(values.document.pages[page][region] as Region).heading}
          onChange={(event) =>
            document({
              ...values.document,
              pages: values.document.pages.map((item, index) =>
                index === page
                  ? {
                      ...item,
                      [region]: {
                        ...(item[region] as Region),
                        heading: event.target.value,
                      },
                    }
                  : item,
              ),
            })
          }
        />
      </label>
      <StructuredReferences
        context={context}
        family={family}
        insert={citation}
      />
    </fieldset>
  );
}
