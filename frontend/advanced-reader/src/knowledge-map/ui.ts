export function element<K extends keyof HTMLElementTagNameMap>(
  tag: K,
  text = "",
  className = "",
): HTMLElementTagNameMap[K] {
  const node = document.createElement(tag);
  node.textContent = text;
  node.className = className;
  return node;
}
export function button(
  text: string,
  action: () => void,
  parent: HTMLElement,
  primary = false,
): HTMLButtonElement {
  const node = element("button", text, primary ? "primary" : "");
  node.type = "button";
  node.onclick = action;
  parent.append(node);
  return node;
}
export function field(
  parent: HTMLElement,
  labelText: string,
  value: string,
  update: (value: string) => void,
  multiline = false,
): HTMLInputElement | HTMLTextAreaElement {
  const label = element("label", labelText),
    input = multiline ? element("textarea") : element("input");
  input.setAttribute("aria-label", labelText);
  input.value = value;
  input.oninput = () => update(input.value);
  label.append(input);
  parent.append(label);
  return input;
}
export function selector(
  parent: HTMLElement,
  labelText: string,
  options: { value: string; text: string }[],
  value: string,
  update: (value: string) => void,
): HTMLSelectElement {
  const label = element("label", labelText),
    select = element("select");
  select.setAttribute("aria-label", labelText);
  options.forEach((option) => {
    const node = element("option", option.text);
    node.value = option.value;
    select.append(node);
  });
  select.value = value;
  select.onchange = () => update(select.value);
  label.append(select);
  parent.append(label);
  return select;
}
