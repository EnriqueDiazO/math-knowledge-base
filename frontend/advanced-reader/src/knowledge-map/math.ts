import { MathfieldElement, validateLatex } from "mathlive";
import DOMPurify from "dompurify";
import fontCss from "mathlive/fonts.css?inline";

// No compute engine, sounds or CDN. Prose and result blocks are rendered by the
// shared document adapter; MathLive only owns mathematical expressions.
MathfieldElement.fontsDirectory = null;
MathfieldElement.soundsDirectory = null;
MathfieldElement.computeEngine = null;
// MathLive's keyboard sink needs contenteditable. DOMPurify deliberately omits
// that attribute by default; stripping it leaves a focused but inert mathfield.
// This hook only receives MathLive's generated markup, never document HTML.
MathfieldElement.createHTML = (html) =>
  DOMPurify.sanitize(html, { ADD_ATTR: ["contenteditable"] });
MathfieldElement.openUrl = () => {};
let fontsStarted = false;
function fonts(): void {
  if (fontsStarted || typeof FontFace === "undefined") return;
  fontsStarted = true;
  const sheet = new CSSStyleSheet();
  sheet.replaceSync(fontCss);
  for (const rule of sheet.cssRules) {
    if (rule.type !== 5) continue;
    const style = (rule as CSSFontFaceRule).style;
    const face = new FontFace(
      style.getPropertyValue("font-family").replaceAll('"', ""),
      style.getPropertyValue("src"),
      {
        weight: style.getPropertyValue("font-weight"),
        style: style.getPropertyValue("font-style"),
      },
    );
    document.fonts.add(face);
    void face.load().catch(() => {
      fontsStarted = false;
    });
  }
}
export function makeMath(latex: string, editable: boolean): MathfieldElement {
  fonts();
  const field = new MathfieldElement();
  field.mathVirtualKeyboardPolicy = "manual";
  field.readOnly = !editable;
  field.value = latex;
  field.setAttribute(
    "aria-label",
    editable ? "Fórmula editable" : "Expresión matemática",
  );
  return field;
}
export function mathErrors(latex: string): string[] {
  try {
    const errors: string[] = validateLatex(latex).map((error) => error.code);
    if (
      !latex.trim() ||
      latex.includes("\\placeholder") ||
      /(?:[_^]|\\frac|\\sqrt)\s*$/u.test(latex)
    )
      errors.push("incomplete-expression");
    return [...new Set(errors)];
  } catch {
    return ["unsupported-expression"];
  }
}
