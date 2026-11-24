/** Unit tests use CodeMirror's public state API; browser tests exercise actual input/copy. */
import { EditorView } from "@codemirror/view";
export function sourceRoot(host: HTMLElement) {
  return host.querySelector(".latex-source-viewport")?.shadowRoot ?? host;
}
export function sourceView(host: HTMLElement) {
  const content = sourceRoot(host).querySelector<HTMLElement>(
    '[aria-label="Fuente LaTeX"]',
  );
  if (!content) throw new Error("Source surface is not mounted");
  const view = EditorView.findFromDOM(content);
  if (!view) throw new Error("CodeMirror view is not mounted");
  return view;
}
export const readSource = (host: HTMLElement) =>
  sourceView(host).state.sliceDoc();
export function writeSource(host: HTMLElement, value: string) {
  const view = sourceView(host);
  view.dispatch({
    changes: { from: 0, to: view.state.doc.length, insert: value },
  });
}
