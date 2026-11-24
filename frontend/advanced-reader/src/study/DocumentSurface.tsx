/** Mount the existing mathematical editor/reader in a wide, owned page surface. */
import { useEffect, useRef } from "react";
import "../knowledge-map/style.css";
import {
  DocumentEditor,
  renderDocument,
} from "../knowledge-map/document-editor";
import type { EditorSnapshot } from "../knowledge-map/document-editor";
import type { StudyContext } from "./api";
import { FigurePreview } from "./FigurePreview";

export function DocumentContent({
  content,
  context,
}: {
  content: string;
  context?: StudyContext;
}) {
  const host = useRef<HTMLDivElement>(null);
  const library = context?.library_id,
    runtime = context?.runtime_id;
  useEffect(() => {
    if (!host.current) return;
    const previews =
      library && runtime
        ? new FigurePreview({ library_id: library, runtime_id: runtime })
        : undefined;
    const cleanup = renderDocument(host.current, content, previews?.show);
    return () => {
      cleanup();
      previews?.destroy();
    };
  }, [content, library, runtime]);
  return <div className="reading-document" ref={host} />;
}
export function DocumentSurface({
  initial,
  snapshot,
  changed,
  editorRef,
  context,
}: {
  initial: string;
  snapshot?: EditorSnapshot;
  changed: (value: string, snapshot: EditorSnapshot) => void;
  editorRef: { current: DocumentEditor | null };
  context?: StudyContext;
}) {
  const host = useRef<HTMLDivElement>(null),
    viewport = useRef<HTMLDivElement>(null);
  const library = context?.library_id,
    runtime = context?.runtime_id;
  const onChange = useRef(changed);
  useEffect(() => {
    onChange.current = changed;
  }, [changed]);
  useEffect(() => {
    if (!host.current || !viewport.current) return;
    const previews =
      library && runtime
        ? new FigurePreview({ library_id: library, runtime_id: runtime })
        : undefined;
    const editor = new DocumentEditor(
      host.current,
      initial,
      (value, state) => onChange.current(value, state),
      snapshot,
      {
        viewport: viewport.current,
        keyboardContainer: viewport.current,
        preview: previews?.show,
      },
    );
    editorRef.current = editor;
    editor.restoreViewport();
    if (snapshot) editor.restoreFocus();
    const remember = () => onChange.current(editor.value(), editor.snapshot());
    const surface = viewport.current;
    surface.addEventListener("scroll", remember);
    return () => {
      remember();
      surface.removeEventListener("scroll", remember);
      editor.destroy();
      previews?.destroy();
      editorRef.current = null;
    };
  }, [initial, snapshot, editorRef, library, runtime]);
  return (
    <div className="study-document-viewport" ref={viewport}>
      <div ref={host} />
    </div>
  );
}
