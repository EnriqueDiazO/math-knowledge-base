import tokens from "../../../../editor/ui/study_theme.json";
export const studyTheme = tokens;
export function applyStudyTheme(root: HTMLElement): void {
  Object.entries(tokens).forEach(([name, value]) =>
    root.style.setProperty("--mm-" + name, value),
  );
}
export function luminance(hex: string): number {
  const values = hex
    .replace("#", "")
    .match(/../gu)!
    .map((v) => parseInt(v, 16) / 255)
    .map((v) => (v <= 0.04045 ? v / 12.92 : ((v + 0.055) / 1.055) ** 2.4));
  return values[0] * 0.2126 + values[1] * 0.7152 + values[2] * 0.0722;
}
export function contrast(a: string, b: string): number {
  const values = [luminance(a), luminance(b)].sort((x, y) => y - x);
  return (values[0] + 0.05) / (values[1] + 0.05);
}
