import { render, waitFor } from "@testing-library/react";
import { expect, it, vi } from "vitest";
import { DocumentSurface } from "../src/study/DocumentSurface";
import type { DocumentEditor } from "../src/knowledge-map/document-editor";
import type { StudyContext } from "../src/study/api";
vi.mock("../src/knowledge-map/math", () => ({
  makeMath: () => document.createElement("math-field"),
  mathErrors: () => [],
}));
vi.mock("../src/knowledge-map/keyboard", () => ({
  mountMathKeyboard: () => () => {},
}));
it("keeps the live document and selection when preparation changes within the same library", async () => {
  const context = {
    library_id: "a",
    runtime_id: "r",
    preparation: { notes_ready: false },
  } as StudyContext;
  const editorRef: { current: DocumentEditor | null } = { current: null };
  const changed = vi.fn(),
    fetch = vi.fn();
  vi.stubGlobal("fetch", fetch);
  const view = render(
    <DocumentSurface
      context={context}
      initial=""
      changed={changed}
      editorRef={editorRef}
    />,
  );
  await waitFor(() => expect(editorRef.current).not.toBeNull());
  const original = editorRef.current!;
  original.editor.commands.insertContent("Mi texto antes de preparar.");
  view.rerender(
    <DocumentSurface
      context={{
        ...context,
        preparation: { ...context.preparation, notes_ready: true },
      }}
      initial=""
      changed={changed}
      editorRef={editorRef}
    />,
  );
  expect(editorRef.current).toBe(original);
  expect(editorRef.current!.value()).toContain("Mi texto antes de preparar.");
  expect(fetch).not.toHaveBeenCalled();
  view.unmount();
  expect(original.editor.isDestroyed).toBe(true);
  vi.unstubAllGlobals();
});
