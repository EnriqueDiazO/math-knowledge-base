import tokens from "../../../../editor/ui/study_theme.json";
import lightTokens from "../../../../editor/ui/study_theme_light.json";
import { applyConceptTheme, conceptTypes } from "./concept-types";
import "./concept-types.css";
export const studyTheme = tokens;
export function applyStudyTheme(
  root: HTMLElement,
  mode: "dark" | "light" = root.ownerDocument.documentElement.dataset
    .appearance === "light"
    ? "light"
    : "dark",
): void {
  applyConceptTheme(root);
  Object.entries(mode === "light" ? lightTokens : tokens).forEach(
    ([name, value]) => root.style.setProperty("--mm-" + name, value),
  );
  if (mode === "light")
    for (const [key, type] of Object.entries(conceptTypes)) {
      let accent = type.original;
      for (
        let i = 0;
        i < 14 && contrast(accent, lightTokens.control) < 4.5;
        i++
      )
        accent =
          "#" +
          accent
            .slice(1)
            .match(/../gu)!
            .map((value) =>
              Math.round(Number.parseInt(value, 16) * 0.8)
                .toString(16)
                .padStart(2, "0"),
            )
            .join("");
      root.style.setProperty(`--concept-${key}-accent`, accent);
      root.style.setProperty(`--concept-${key}-border`, accent + "66");
      root.style.setProperty(`--concept-${key}-background`, accent + "0c");
    }
}
export function luminance(hex: string): number {
  const values = hex
    .replace("#", "")
    .match(/../gu)!
    .map((v) => Number.parseInt(v, 16) / 255)
    .map((v) => (v <= 0.04045 ? v / 12.92 : ((v + 0.055) / 1.055) ** 2.4));
  return values[0] * 0.2126 + values[1] * 0.7152 + values[2] * 0.0722;
}
export function contrast(a: string, b: string): number {
  const values = [luminance(a), luminance(b)].sort((x, y) => y - x);
  return (values[0] + 0.05) / (values[1] + 0.05);
}
