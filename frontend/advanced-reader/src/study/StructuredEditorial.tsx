/** Shared presentation of existing Cornell/CPI footer and watermark contracts. */
import type { DocumentChange, StructuredDocument } from "./structured-state";
type Footer = {
  enabled?: boolean;
  mode?: string;
  text?: string;
  author?: string;
  course?: string;
  year?: string;
  position?: string;
};
type Watermark = {
  enabled?: boolean;
  type?: string;
  text?: string;
  opacity?: number;
  scale?: number;
  position?: string;
  all_pages?: boolean;
};
function Position({
  label,
  value,
  change,
}: {
  label: string;
  value: string;
  change: (value: string) => void;
}) {
  return (
    <label>
      {label}
      <select
        aria-label={label}
        value={value}
        onChange={(event) => change(event.target.value)}
      >
        <option value="center">Centro</option>
        <option value="bottom_right">Abajo a la derecha</option>
        <option value="top_right">Arriba a la derecha</option>
      </select>
    </label>
  );
}
export function StructuredEditorial({
  value,
  change,
}: {
  value: StructuredDocument;
  change: DocumentChange;
}) {
  const footer = (value.attribution ?? {}) as Footer;
  const watermark = (value.watermark ?? {}) as Watermark;
  const patch = (
    section: "attribution" | "watermark",
    key: string,
    value: string | boolean | number,
  ) =>
    change((current) => ({
      ...current,
      [section]: { ...((current[section] as object) ?? {}), [key]: value },
    }));
  return (
    <details className="structured-editorial">
      <summary>Pie de página y marca de agua</summary>
      <p>
        Estas opciones se conservan con la nota y se aplican al exportar. El
        contenido de las regiones permanece intacto.
      </p>
      <fieldset>
        <legend>Pie de página</legend>
        <label>
          <input
            type="checkbox"
            checked={!!footer.enabled}
            onChange={(event) =>
              patch("attribution", "enabled", event.target.checked)
            }
          />
          Incluir pie de página
        </label>
        <label>
          Contenido del pie
          <select
            aria-label="Contenido del pie"
            value={footer.mode || "auto"}
            onChange={(event) =>
              patch("attribution", "mode", event.target.value)
            }
          >
            <option value="auto">Autor, curso y año</option>
            <option value="custom">Texto propio</option>
          </select>
        </label>
        {footer.mode === "custom" ? (
          <label>
            Texto del pie
            <input
              value={footer.text || ""}
              onChange={(event) =>
                patch("attribution", "text", event.target.value)
              }
            />
          </label>
        ) : (
          (
            [
              ["author", "Autor del pie"],
              ["course", "Curso del pie"],
              ["year", "Año del pie"],
            ] as const
          ).map(([key, label]) => (
            <label key={key}>
              {label}
              <input
                value={footer[key] || ""}
                onChange={(event) =>
                  patch("attribution", key, event.target.value)
                }
              />
            </label>
          ))
        )}
        <Position
          label="Posición del pie"
          value={footer.position || "bottom_right"}
          change={(position) => patch("attribution", "position", position)}
        />
      </fieldset>
      <fieldset>
        <legend>Marca de agua</legend>
        <label>
          <input
            type="checkbox"
            checked={!!watermark.enabled}
            onChange={(event) =>
              patch("watermark", "enabled", event.target.checked)
            }
          />
          Incluir marca de agua
        </label>
        {watermark.type === "image" ? (
          <p>
            Se conserva la imagen de marca de agua de esta nota. Su sustitución
            desde React sigue pendiente.
          </p>
        ) : (
          <label>
            Texto de la marca de agua
            <input
              value={watermark.text || ""}
              onChange={(event) =>
                patch("watermark", "text", event.target.value)
              }
            />
          </label>
        )}
        {(
          [
            ["opacity", "Opacidad de la marca", 0, 1, 0.01, 0.05],
            ["scale", "Escala de la marca", 0.05, 2, 0.05, 0.4],
          ] as const
        ).map(([key, label, min, max, step, fallback]) => (
          <label key={key}>
            {label}
            <input
              type="number"
              min={min}
              max={max}
              step={step}
              value={watermark[key] ?? fallback}
              onChange={(event) => {
                if (Number.isFinite(event.target.valueAsNumber))
                  patch("watermark", key, event.target.valueAsNumber);
              }}
            />
          </label>
        ))}
        <Position
          label="Posición de la marca"
          value={watermark.position || "center"}
          change={(position) => patch("watermark", "position", position)}
        />
        <label>
          <input
            type="checkbox"
            checked={watermark.all_pages ?? true}
            onChange={(event) =>
              patch("watermark", "all_pages", event.target.checked)
            }
          />
          Marca en todas las páginas
        </label>
      </fieldset>
    </details>
  );
}
