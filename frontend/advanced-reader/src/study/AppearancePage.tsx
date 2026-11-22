import { conceptTypes } from "../knowledge-map/concept-types";
import { DocumentContent } from "./DocumentSurface";
import { ConceptTypeBadge } from "./ConceptTypeBadge";
import "./appearance.css";
import { conceptSample } from "./concept-sample";

export default function AppearancePage() {
  return (
    <section className="study-appearance">
      <header>
        <p className="eyebrow">Identidad de MathMongo</p>
        <h1>Tipos matemáticos</h1>
        <p>
          Las cajas de nuestras notas LaTeX orientan el editor, los conceptos y
          las esferas. Cada tipo conserva su nombre y un símbolo, además de su
          color.
        </p>
      </header>
      <div
        className="concept-palette"
        aria-label="Paleta original y adaptación para pantalla"
      >
        {Object.entries(conceptTypes).map(([key, type]) => (
          <article key={key}>
            <ConceptTypeBadge type={key} />
            <p>
              <span
                className="color-swatch"
                style={{ background: type.original }}
              />{" "}
              LaTeX · {type.latex} · {type.original}
            </p>
            <p>
              <span
                className="color-swatch"
                style={{ background: type.accent }}
              />{" "}
              Pantalla · {type.accent}
            </p>
          </article>
        ))}
      </div>
      <p>
        <code>remark</code> es Nota. El púrpura de xcolor es rojizo. Proposición
        usa naranja suave y un rombo; Ejemplo, naranja intenso y un cuadrado.
      </p>
      <DocumentContent content={conceptSample} />
      <p>
        Estas son adaptaciones para el tema oscuro. La exportación y los estilos
        personalizados de los documentos conservan sus valores originales.
      </p>
    </section>
  );
}
