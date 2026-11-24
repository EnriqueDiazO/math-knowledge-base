import { afterEach, expect, it, vi } from "vitest";
import { LatexSourceEditor } from "../src/latex/source-editor";
import type { LatexSourceLoader as Loader } from "../src/latex/source-loader";
const { LatexSourceLoader } = await vi.importActual<
  typeof import("../src/latex/source-loader")
>("../src/latex/source-loader");
const instances: Loader[] = [];
afterEach(() => {
  instances.forEach((value) => value.destroy());
  instances.length = 0;
  document.body.replaceChildren();
});
function mount(
  load: () => Promise<{ LatexSourceEditor: typeof LatexSourceEditor }>,
) {
  const host = document.createElement("section");
  document.body.append(host);
  const changed = vi.fn(),
    editor = new LatexSourceLoader(
      host,
      "Fuente original\r\n\\unknown{á}",
      changed,
      load,
    );
  instances.push(editor);
  return { editor, host, changed };
}
it("keeps canonical source and cursor before tools load, then uses the latest draft", async () => {
  let complete!: (module: {
    LatexSourceEditor: typeof LatexSourceEditor;
  }) => void;
  const load = vi.fn(
    () =>
      new Promise<{ LatexSourceEditor: typeof LatexSourceEditor }>((done) => {
        complete = done;
      }),
  );
  const { editor, host } = mount(load);
  expect(load).not.toHaveBeenCalled();
  editor.restore({ anchor: 2, head: 5, scrollTop: 12, scrollLeft: 0 });
  editor.focus();
  editor.focus();
  expect(load).toHaveBeenCalledTimes(1);
  editor.value = "Nueva fuente\r\n\\unknown{á}";
  complete({ LatexSourceEditor });
  await vi.waitFor(() =>
    expect(host.querySelector(".cm-editor")).not.toBeNull(),
  );
  expect(editor.value).toBe("Nueva fuente\r\n\\unknown{á}");
  expect(editor.snapshot()).toMatchObject({ anchor: 2, head: 5 });
});
it("does not load or mount anything when the owner has already closed", async () => {
  const load = vi.fn(async () => ({ LatexSourceEditor }));
  const { editor, host } = mount(load);
  editor.destroy();
  editor.focus();
  expect(load).not.toHaveBeenCalled();
  expect(host.childElementCount).toBe(0);
});
it("ignores a late successful import after closing the owning page", async () => {
  let complete!: (module: {
    LatexSourceEditor: typeof LatexSourceEditor;
  }) => void;
  const { editor, host, changed } = mount(
    () =>
      new Promise((done) => {
        complete = done;
      }),
  );
  editor.focus();
  editor.destroy();
  complete({ LatexSourceEditor });
  await Promise.resolve();
  await Promise.resolve();
  expect(host.childElementCount).toBe(0);
  expect(changed).not.toHaveBeenCalled();
});
it("preserves exact source on load failure and permits an explicit retry", async () => {
  const load = vi
    .fn()
    .mockRejectedValueOnce(new Error("Missing chunk"))
    .mockResolvedValue({ LatexSourceEditor });
  const { editor, host } = mount(load);
  const source = editor.value;
  editor.focus();
  await vi.waitFor(() =>
    expect(host.querySelector('[role="alert"]')).not.toBeNull(),
  );
  expect(editor.value).toBe(source);
  expect(host.querySelector("textarea")!.readOnly).toBe(true);
  host.querySelector<HTMLButtonElement>("button")!.click();
  await vi.waitFor(() =>
    expect(host.querySelector(".cm-editor")).not.toBeNull(),
  );
  expect(editor.value).toBe(source);
  expect(load).toHaveBeenCalledTimes(2);
});
it("ignores a late rejected import after closing, without inserting an orphan warning", async () => {
  let fail!: (reason: Error) => void;
  const { editor, host } = mount(
    () =>
      new Promise((_resolve, reject) => {
        fail = reject;
      }),
  );
  editor.focus();
  editor.destroy();
  fail(new Error("Disconnected"));
  await Promise.resolve();
  await Promise.resolve();
  expect(host.childElementCount).toBe(0);
});
