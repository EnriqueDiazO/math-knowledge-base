/** Mount the vendor keyboard through its public API, inside our own dialog.
 * MathLive installs constructed styles on document; a CCv2 ShadowRoot needs to
 * adopt the same sheets. Public keyboard events delimit that synchronous change,
 * so this adapter needs no vendor selectors or Streamlit parent-DOM queries.
 */
const keyboardSheets = new Set<CSSStyleSheet>();
export function mountMathKeyboard(container: HTMLElement): () => void {
  const keyboard = window.mathVirtualKeyboard;
  if (!keyboard) return () => {};
  const host = document.createElement("div");
  host.className = "math-keyboard-host";
  host.style.cssText =
    "position:sticky;bottom:0;height:min(36dvh,320px);width:100%;z-index:10;grid-template-rows:auto minmax(0,1fr);--keycap-height:min(5dvh,44px);--keycap-font-size:22px;display:none";
  host.hidden = true;
  const close = document.createElement("button");
  close.type = "button";
  close.textContent = "Ocultar teclado matemático";
  close.onmousedown = (event) => event.preventDefault();
  close.onclick = () => keyboard.hide();
  const frame = document.createElement("div");
  frame.style.minHeight = "0";
  host.append(close, frame);
  container.append(host);
  let before = new Set(document.adoptedStyleSheets ?? []);
  const prepare = () => {
    before = new Set(document.adoptedStyleSheets ?? []);
  };
  const adopt = () => {
    host.hidden = !keyboard.visible;
    host.style.display = keyboard.visible ? "grid" : "none";
    const root = host.getRootNode();
    if (!(root instanceof ShadowRoot) || !("adoptedStyleSheets" in root))
      return;
    for (const sheet of document.adoptedStyleSheets ?? [])
      if (!before.has(sheet)) keyboardSheets.add(sheet);
    root.adoptedStyleSheets = [
      ...new Set([...root.adoptedStyleSheets, ...keyboardSheets]),
    ];
  };
  keyboard.container = frame;
  keyboard.addEventListener?.("before-virtual-keyboard-toggle", prepare);
  keyboard.addEventListener?.("virtual-keyboard-toggle", adopt);
  adopt();
  return () => {
    keyboard.hide();
    keyboard.removeEventListener?.("before-virtual-keyboard-toggle", prepare);
    keyboard.removeEventListener?.("virtual-keyboard-toggle", adopt);
    if (keyboard.container === frame) keyboard.container = document.body;
    host.remove();
  };
}
