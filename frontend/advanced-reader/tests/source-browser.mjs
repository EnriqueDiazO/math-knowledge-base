/** Exercise public clipboard/keyboard behavior; never read private CodeMirror fields. */
export const sourceField = (page) =>
  page.getByRole("textbox", { name: "Fuente LaTeX", exact: true });
function transfer(element, { mode, text = "" }) {
  const data = new DataTransfer();
  if (mode === "paste") data.setData("text/plain", text);
  const event = new ClipboardEvent(mode, {
    clipboardData: data,
    bubbles: true,
    cancelable: true,
  });
  // Firefox drops the supplied data on synthetic clipboard events.
  if (event.clipboardData !== data)
    Object.defineProperty(event, "clipboardData", { value: data });
  element.dispatchEvent(event);
  return data.getData("text/plain");
}
export async function readSource(page) {
  const field = sourceField(page);
  await field.press("ControlOrMeta+a");
  const text = await field.evaluate(transfer, { mode: "copy" });
  await field.press("ArrowLeft");
  return text;
}
export async function writeSource(page, text) {
  const field = sourceField(page);
  await field.press("ControlOrMeta+a");
  await field.evaluate(transfer, { mode: "paste", text });
}
