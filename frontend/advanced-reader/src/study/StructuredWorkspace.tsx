/** One shared mathematical editor, explicitly scoped to one academic page and region. */
import { useRef, useState } from "react";
import type {
  DocumentEditor,
  EditorSnapshot,
} from "../knowledge-map/document-editor";
import { studyRequest, StudyApiError, type StudyContext } from "./api";
import { DocumentSurface } from "./DocumentSurface";
import { ExportActions } from "./ExportActions";
import { StudyLink } from "./StudyLink";
import { StructuredFields } from "./StructuredFields";
import { useLocalForm } from "./useLocalForm";
import { useOperationScope } from "./useOperationScope";
import type { Navigate } from "./navigation";
import {
  structuredDraft,
  structuredValues,
  structuredRequest,
  orderedPages,
  emptyPage,
  regions,
  sameStructuredValue,
  type Family,
  type Region,
  type Metadata,
  type StructuredDetail,
  type StructuredDraft,
} from "./structured-state";

export function StructuredWorkspace({
  context,
  family,
  note,
  navigate,
}: {
  context: StudyContext;
  family: Family;
  note?: StructuredDetail;
  navigate: Navigate;
}) {
  const form = useLocalForm(
      "mathmongo-structured-v1-" +
        context.library_id +
        "-" +
        family +
        "-" +
        (note?.note_id || "new"),
      () => structuredDraft(family, note),
    ),
    current = useRef(form.state),
    editor = useRef<DocumentEditor | null>(null),
    scope = useOperationScope(context),
    finished = useRef(false),
    token = useRef(0);
  const title = family === "cornell" ? "Cornell" : "CPI",
    path =
      "/structured/" +
      family +
      (note ? "/" + encodeURIComponent(note.note_id) : "");
  const [page, setPage] = useState(0),
    [region, setRegion] = useState<string>(regions[family][0][0]),
    [epoch, setEpoch] = useState(0),
    [busy, setBusy] = useState(false),
    [message, setMessage] = useState(""),
    [conflict, setConflict] = useState(false),
    [remote, setRemote] = useState<StructuredDetail>(),
    [remove, setRemove] = useState(false),
    [savedSource, setSavedSource] = useState(note?.latex_body || "");
  const [surface, setSurface] = useState(() => {
    try {
      const value = structuredValues(form.state, family),
        key = value.keys[0] + ":" + regions[family][0][0];
      return {
        initial: (value.document.pages[0][regions[family][0][0]] as Region)
          .latex,
        snapshot: value.snapshots[key],
      };
    } catch {
      return { initial: "", snapshot: undefined };
    }
  });
  const remember = (draft: StructuredDraft) => {
    if (finished.current) return true;
    current.current = draft;
    return form.set(draft);
  };
  let problem = "",
    values: ReturnType<typeof structuredValues> | undefined;
  try {
    values = structuredValues(form.state, family);
    structuredRequest(form.state, family, !!note);
    if (form.state.pending) JSON.parse(form.state.pending);
  } catch (error) {
    problem = (error as Error).message;
  }
  const updateRegion = (
    latex: string,
    snapshot: EditorSnapshot,
    selectedPage = page,
    selectedRegion = region,
  ) => {
    const value = structuredValues(current.current, family),
      document = value.document,
      key = value.keys[selectedPage] + ":" + selectedRegion;
    document.pages[selectedPage][selectedRegion] = {
      ...(document.pages[selectedPage][selectedRegion] as Region),
      latex,
    };
    remember({
      ...current.current,
      document: JSON.stringify(document),
      snapshots: JSON.stringify({ ...value.snapshots, [key]: snapshot }),
    });
  };
  const flush = () => {
    if (!editor.current?.valid()) {
      setMessage(
        "Completa la fórmula antes de cambiar de región o guardar. El borrador se conserva.",
      );
      return false;
    }
    updateRegion(editor.current.value(), editor.current.snapshot());
    return true;
  };
  const activate = (index: number, key: string) => {
    const value = structuredValues(current.current, family);
    token.current += 1;
    setEpoch(token.current);
    setPage(index);
    setRegion(key);
    setRemove(false);
    setSurface({
      initial: (value.document.pages[index][key] as Region).latex,
      snapshot: value.snapshots[value.keys[index] + ":" + key],
    });
  };
  const changeMetadata = (key: keyof Metadata, value: string | string[]) => {
    const data = structuredValues(current.current, family);
    remember({
      ...current.current,
      metadata: JSON.stringify({ ...data.metadata, [key]: value }),
    });
  };
  const changePages = (
    operation: "add" | "duplicate" | "up" | "down" | "remove",
  ) => {
    if (!flush()) return;
    const value = structuredValues(current.current, family),
      pages = value.document.pages;
    let next: number;
    if (operation === "add" || operation === "duplicate") {
      const newPage =
        operation === "add" ? emptyPage(family) : structuredClone(pages[page]);
      if (family === "cornell") newPage.page_id = crypto.randomUUID();
      pages.splice(page + 1, 0, newPage);
      value.keys.splice(page + 1, 0, crypto.randomUUID());
      value.origins.splice(
        page + 1,
        0,
        operation === "add" ? null : value.origins[page],
      );
      next = page + 1;
    } else if (operation === "remove") {
      pages.splice(page, 1);
      value.keys.splice(page, 1);
      value.origins.splice(page, 1);
      next = Math.min(page, pages.length - 1);
    } else {
      next = page + (operation === "up" ? -1 : 1);
      for (const list of [pages, value.keys, value.origins])
        [list[page], list[next]] = [list[next], list[page]];
    }
    value.document.pages = orderedPages(pages, family);
    remember({
      ...current.current,
      document: JSON.stringify(value.document),
      keys: JSON.stringify(value.keys),
      origins: JSON.stringify(value.origins),
    });
    activate(next, region);
  };
  const save = async () => {
    if (busy || problem || form.problem || conflict) return;
    if (!current.current.pending) {
      if (!flush()) return;
      const value = structuredValues(current.current, family);
      if (
        !value.metadata.title?.trim() &&
        (!note ||
          value.metadata.title !==
            (JSON.parse(current.current.original) as { metadata: Metadata })
              .metadata.title)
      ) {
        setMessage("Escribe un título; el borrador se conserva.");
        return;
      }
      if (
        !remember({
          ...current.current,
          pending: JSON.stringify(
            structuredRequest(current.current, family, !!note),
          ),
        })
      )
        return;
    }
    setBusy(true);
    setMessage("Guardando nota… esperando confirmación de la biblioteca.");
    try {
      const result = await studyRequest<StructuredDetail>(
        path,
        context,
        JSON.parse(current.current.pending),
      );
      if (!scope.active) return;
      const value = structuredValues(current.current, family);
      if (
        !sameStructuredValue(result.document, value.document) ||
        Object.entries(value.metadata).some(
          ([key, val]) =>
            !sameStructuredValue(result.metadata[key as keyof Metadata], val),
        )
      )
        throw new Error(
          "El contenido no se confirmó. El borrador y el intento se conservan; consulta la nota antes de reintentar.",
        );
      if (!note) {
        finished.current = true;
        form.clear();
        navigate(
          "/study/notebook/" +
            family +
            "/" +
            encodeURIComponent(result.note_id),
        );
        return;
      }
      const next = {
        ...structuredDraft(family, result),
        snapshots: current.current.snapshots,
        keys: current.current.keys,
      };
      remember(next);
      setSavedSource(result.latex_body);
      setMessage("Nota guardada y confirmada en esta biblioteca.");
    } catch (error) {
      if (!scope.active) return;
      if (
        error instanceof StudyApiError &&
        [
          "catalog_conflict",
          "invalid_study_request",
          "invalid_structured_document",
        ].includes(error.code)
      ) {
        remember({ ...current.current, pending: "" });
        setConflict(!!note && error.code === "catalog_conflict");
      }
      setMessage((error as Error).message);
    } finally {
      if (scope.active) setBusy(false);
    }
  };
  const locked =
    busy || !!form.state.pending || conflict || !!problem || !!form.problem;
  return (
    <section className={"study-structured study-structured-" + family}>
      <StudyLink to={"/study/notebook/" + family} navigate={navigate}>
        Volver a {title}
      </StudyLink>
      <p className="eyebrow">{title} · Regiones académicas · LaTeX canónico</p>
      <h1>
        {note ? "Editar nota " : "Nueva nota "}
        {title}
      </h1>
      <p role="status">
        {message ||
          "Borrador conservado en este navegador. Guardar lo confirma en esta biblioteca."}
      </p>
      {(problem || form.problem) && (
        <p role="alert">
          {problem || form.problem}
          <button onClick={form.download}>Descargar borrador</button>
          <button
            onClick={() => {
              if (form.restart()) {
                remember(structuredDraft(family, note));
                activate(0, regions[family][0][0]);
                setConflict(false);
                setRemote(undefined);
              }
            }}
          >
            Reiniciar con copia
          </button>
        </p>
      )}
      {values && (
        <>
          <StructuredFields
            context={context}
            family={family}
            values={values}
            page={page}
            region={region}
            locked={locked}
            remove={remove}
            setRemove={setRemove}
            metadata={changeMetadata}
            changePages={changePages}
            select={(index, key) => {
              if (flush()) activate(index, key);
            }}
            document={(document) =>
              remember({
                ...current.current,
                document: JSON.stringify(document),
              })
            }
            citation={(latex) => {
              if (!flush()) return false;
              const value = structuredValues(current.current, family),
                key = value.keys[page] + ":" + region;
              value.document.pages[page][region] = {
                ...(value.document.pages[page][region] as Region),
                latex:
                  (value.document.pages[page][region] as Region).latex +
                  "\n\n" +
                  latex,
              };
              delete value.snapshots[key];
              remember({
                ...current.current,
                document: JSON.stringify(value.document),
                snapshots: JSON.stringify(value.snapshots),
              });
              activate(page, region);
              return true;
            }}
          />
          {!problem && !form.problem && (
            <div inert={locked}>
              <DocumentSurface
                key={epoch}
                initial={surface.initial}
                snapshot={surface.snapshot}
                context={context}
                title={(values.document.pages[page][region] as Region).heading}
                editorRef={editor}
                changed={(latex, state) => {
                  if (token.current === epoch) updateRegion(latex, state);
                }}
              />
            </div>
          )}
        </>
      )}
      <div className="study-actions">
        <button
          className="primary-button"
          disabled={busy || conflict || !!problem || !!form.problem}
          onClick={() => void save()}
        >
          {form.state.pending
            ? "Reintentar el mismo guardado"
            : "Guardar nota " + title}
        </button>
        <button onClick={form.download}>Descargar borrador</button>
      </div>
      {conflict && (
        <section aria-label="Conflicto de la nota">
          <p>
            Tu trabajo local permanece intacto. Consulta la nota actual antes de
            reemplazar el borrador.
          </p>
          <button
            onClick={async () => {
              try {
                const value = await studyRequest<StructuredDetail>(
                  path,
                  context,
                );
                if (scope.active) setRemote(value);
              } catch (error) {
                if (scope.active) setMessage((error as Error).message);
              }
            }}
          >
            Consultar versión guardada
          </button>
          {remote && (
            <>
              <pre>{remote.latex_body}</pre>
              <button
                onClick={() => {
                  if (!form.restart()) return;
                  remember(structuredDraft(family, remote));
                  setSavedSource(remote.latex_body);
                  activate(0, regions[family][0][0]);
                  setConflict(false);
                  setRemote(undefined);
                  setMessage(
                    "Borrador anterior archivado. Se abrió la versión guardada; no se publicó contenido nuevo.",
                  );
                }}
              >
                Archivar borrador y abrir versión guardada
              </button>
            </>
          )}
        </section>
      )}
      {note && (
        <>
          <details>
            <summary>Fuente documental guardada</summary>
            <pre>{savedSource}</pre>
          </details>
          <ExportActions
            context={context}
            notebookId={note.note_id}
            structuredFamily={family}
          />
          <button
            disabled={busy}
            onClick={async () => {
              setBusy(true);
              try {
                const result = await studyRequest<{ message: string }>(
                  path + "/fit",
                  context,
                  {},
                );
                if (scope.active) setMessage(result.message);
              } catch (error) {
                if (scope.active) setMessage((error as Error).message);
              } finally {
                if (scope.active) setBusy(false);
              }
            }}
          >
            Comprobar ajuste de la nota guardada
          </button>
        </>
      )}
    </section>
  );
}
