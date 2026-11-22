/** Mount the existing mathematical editor/reader in a wide, owned page surface. */
import { useEffect, useRef } from "react";
import "../knowledge-map/style.css";
import {
  DocumentEditor,
  renderDocument,
} from "../knowledge-map/document-editor";
import type { EditorSnapshot } from "../knowledge-map/document-editor";

export function DocumentContent({ content }: { content: string }) {
  const host = useRef<HTMLDivElement>(null);
  useEffect(
    () => (host.current ? renderDocument(host.current, content) : undefined),
    [content],
  );
  return <div className="reading-document" ref={host} />;
}
export function DocumentSurface({
  initial,
  snapshot,
  changed,
  editorRef,
}: {
  initial: string;
  snapshot?: EditorSnapshot;
  changed: (value: string, snapshot: EditorSnapshot) => void;
  editorRef: { current: DocumentEditor | null };
}) {
  const host = useRef<HTMLDivElement>(null),
    viewport = useRef<HTMLDivElement>(null);
  const onChange = useRef(changed);
  useEffect(() => {
    onChange.current = changed;
  }, [changed]);
  useEffect(() => {
    if (!host.current || !viewport.current) return;
    const editor = new DocumentEditor(
      host.current,
      initial,
      (value, state) => onChange.current(value, state),
      snapshot,
      { viewport: viewport.current, keyboardContainer: viewport.current },
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
      editorRef.current = null;
    };
  }, [initial, snapshot, editorRef]);
  return (
    <div className="study-document-viewport" ref={viewport}>
      <div ref={host} />
    </div>
  );
}
