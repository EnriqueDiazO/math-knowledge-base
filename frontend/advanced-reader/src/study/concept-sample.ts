import { conceptTypes } from "../knowledge-map/concept-types";

export const conceptSample = Object.entries(conceptTypes)
  .map(
    ([key, type]) =>
      `\\begin{cth${key}}{${type.label} en el espacio de estudio}\nUna idea con $\\frac{1}{2}$ y $\\int_0^1 x^2\\,dx = \\frac{1}{3}$. El color identifica el tipo; la lectura conserva un fondo estable.\n\\end{cth${key}}`,
  )
  .join("\n\n");
