/** Mount the vendor keyboard through its public API, inside our own dialog.
 * MathLive installs constructed styles on document; a CCv2 ShadowRoot needs to
 * adopt the same sheets. Public keyboard events delimit that synchronous change,
 * so this adapter needs no vendor selectors or Streamlit parent-DOM queries.
 */
const keyboardSheets = new Set<CSSStyleSheet>();
export function mountMathKeyboard(container: HTMLElement): () => void {
  const keyboard = window.mathVirtualKeyboard;
  if (!keyboard) return () => {};
  const previousLayouts = keyboard.layouts;
  keyboard.layouts = ["numeric", "symbols", "alphabetic", "greek"];
  const host = document.createElement("div");
  host.className = "math-keyboard-host";
  host.style.cssText =
    "position:sticky;bottom:0;height:min(43dvh,380px);width:100%;z-index:10;grid-template-rows:auto minmax(0,1fr);--keycap-height:min(4dvh,36px);--keycap-font-size:22px;display:none";
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
  const fit = () => {
    const height = keyboard.boundingRect?.height;
    if (!keyboard.visible || !height || !Number.isFinite(height)) return;
    // boundingRect is the public geometry of the active layout, not the host.
    // Reserve only our close control, its margins and the container border.
    const controlHeight = close.getBoundingClientRect().height || 30;
    host.style.height = Math.ceil(height + controlHeight + 12) + "px";
  };
  const adopt = () => {
    host.hidden = !keyboard.visible;
    host.style.display = keyboard.visible ? "grid" : "none";
    const root = host.getRootNode();
    if (root instanceof ShadowRoot && "adoptedStyleSheets" in root) {
      for (const sheet of document.adoptedStyleSheets ?? [])
        if (!before.has(sheet)) keyboardSheets.add(sheet);
      root.adoptedStyleSheets = [
        ...new Set([...root.adoptedStyleSheets, ...keyboardSheets]),
      ];
    }
    fit();
  };
  keyboard.container = frame;
  keyboard.addEventListener?.("before-virtual-keyboard-toggle", prepare);
  keyboard.addEventListener?.("virtual-keyboard-toggle", adopt);
  keyboard.addEventListener?.("geometrychange", fit);
  adopt();
  return () => {
    keyboard.hide();
    keyboard.removeEventListener?.("before-virtual-keyboard-toggle", prepare);
    keyboard.removeEventListener?.("virtual-keyboard-toggle", adopt);
    keyboard.removeEventListener?.("geometrychange", fit);
    if (keyboard.container === frame) keyboard.container = document.body;
    keyboard.layouts = previousLayouts;
    host.remove();
  };
}
