/** Three persistent Cornell editors, each with its own selection, undo history and canonical body. */
import { useState } from "react";
import type {
  DocumentEditor,
  EditorSnapshot,
} from "../knowledge-map/document-editor";
import { DocumentSurface } from "./DocumentSurface";
import type { StudyContext } from "./api";
import { regions, type Region, type StructuredPage } from "./structured-state";
import "./cornell-regions.css";
export type CornellEditors = Record<string, { current: DocumentEditor | null }>;
export function CornellRegions({
  context,
  page,
  pageKey,
  snapshots,
  editors,
  active,
  select,
  changed,
}: {
  context: StudyContext;
  page: StructuredPage;
  pageKey: string;
  snapshots: Record<string, EditorSnapshot>;
  editors: CornellEditors;
  active: string;
  select: (key: string) => void;
  changed: (key: string, latex: string, snapshot: EditorSnapshot) => void;
}) {
  const [initial] = useState(() =>
    Object.fromEntries(
      regions.cornell.map(([key]) => [
        key,
        {
          latex: (page[key] as Region).latex,
          snapshot: snapshots[pageKey + ":" + key],
        },
      ]),
    ),
  );
  return (
    <div className="cornell-regions" aria-label="Tres regiones Cornell">
      {regions.cornell.map(([key, label]) => (
        <section
          key={key}
          className={"cornell-region cornell-region-" + key}
          aria-label={label}
          data-active={active === key}
          onFocusCapture={() => select(key)}
          onPointerDownCapture={() => select(key)}
        >
          <header>
            <h2>{label}</h2>
            <p>{(page[key] as Region).heading}</p>
            <span>
              {active === key
                ? "Región activa"
                : "Herramientas propias de esta región"}
            </span>
          </header>
          <DocumentSurface
            focusOnRestore={active === key}
            initial={initial[key].latex}
            snapshot={initial[key].snapshot}
            editorRef={editors[key]}
            context={context}
            title={(page[key] as Region).heading}
            changed={(latex, snapshot) => changed(key, latex, snapshot)}
          />
        </section>
      ))}
    </div>
  );
}
