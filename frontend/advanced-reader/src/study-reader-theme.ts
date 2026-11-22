/** Opt-in room presentation; PDF pixels and annotation colors remain untouched. */
import { applyStudyTheme } from "./knowledge-map/theme";
export function configureReaderTheme(root: HTMLElement, search: string): void {
  if (new URLSearchParams(search).get("theme") !== "study") return;
  applyStudyTheme(root);
  root.dataset.studyTheme = "true";
}
