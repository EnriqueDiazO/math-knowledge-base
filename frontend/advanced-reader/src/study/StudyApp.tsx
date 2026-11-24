/** Independent study shell. Pages own their active data and canonical operations. */
import { lazy, Suspense, useEffect, useState } from "react";
import { applyStudyTheme } from "../knowledge-map/theme";
import { studyRequest } from "./api";
import type { StudyContext } from "./api";
import { LibraryPage, SourcePage } from "./LibraryPages";
import { newStudyDraft, studyVault } from "./drafts";
import { useStudyRoute } from "./navigation";
import { StudyLink } from "./StudyLink";
import { useOperationScope } from "./useOperationScope";
import "./study.css";
import "./surfaces.css";
import "./activity-forms.css";

const AppearancePage = lazy(() => import("./AppearancePage"));
const NotebookPages = lazy(() =>
  import("./NotebookPages").then((module) => ({
    default: module.NotebookPages,
  })),
);
const NewSourcePage = lazy(() =>
  import("./SourceForms").then((module) => ({ default: module.NewSourcePage })),
);
const ConceptEditorPage = lazy(() =>
  import("./ConceptWorkspace").then((module) => ({
    default: module.ConceptEditorPage,
  })),
);

const ReadingPage = lazy(() => import("./ReadingPage"));
const NotesPage = lazy(() =>
  import("./NotePages").then((module) => ({ default: module.NotesPage })),
);
const WritePage = lazy(() =>
  import("./NotePages").then((module) => ({ default: module.WritePage })),
);
const SavedNotePage = lazy(() =>
  import("./NotePages").then((module) => ({ default: module.SavedNotePage })),
);
const ConceptPage = lazy(() =>
  import("./ConceptPages").then((module) => ({ default: module.ConceptPage })),
);
const ConceptsPage = lazy(() =>
  import("./ConceptPages").then((module) => ({ default: module.ConceptsPage })),
);
const SpacesPage = lazy(() =>
  import("./ConceptPages").then((module) => ({ default: module.SpacesPage })),
);

const pages = [
  ["Inicio", ""],
  ["Biblioteca", "/library"],
  ["Notas", "/notes"],
  ["Conceptos", "/concepts"],
  ["Espacios", "/spaces"],
  ["Cuaderno", "/notebook"],
  ["Ajustes", "/settings"],
] as const;
export function StudyApp() {
  const [context, setContext] = useState<StudyContext>();
  const scope = useOperationScope(context);
  const [error, setError] = useState(""),
    [notice, setNotice] = useState(""),
    [retry, setRetry] = useState(0);
  const { route, navigate } = useStudyRoute();
  useEffect(() => {
    applyStudyTheme(document.documentElement);
    document.documentElement.dataset.studyTheme = "true";
    const controller = new AbortController();
    studyRequest<StudyContext>(
      "/context",
      undefined,
      undefined,
      controller.signal,
    )
      .then((value) => {
        if (!controller.signal.aborted) {
          setContext(value);
          setError("");
        }
      })
      .catch((reason) => {
        if (!controller.signal.aborted) setError(reason.message);
      });
    return () => controller.abort();
  }, [retry]);
  if (!context)
    return (
      <main className="study-boot">
        <h1>MathMongo</h1>
        {error ? (
          <>
            <p role="alert">{error}</p>
            <button onClick={() => setRetry((value) => value + 1)}>
              Volver a conectar
            </button>
          </>
        ) : (
          <p role="status">Abriendo tu biblioteca…</p>
        )}
      </main>
    );
  const url = new URL(route, location.origin),
    parts = url.pathname.split("/").slice(2).map(decodeURIComponent);
  const section = parts[0] || "",
    identity = parts.slice(1).join("/");
  const prepare = async () => {
    try {
      const checked = await studyRequest<StudyContext>("/prepare", context, {
        version: context.preparation.version,
      });
      if (!scope.active || checked.library_id !== context.library_id) return;
      setContext(checked);
      setNotice(
        checked.preparation.state === "ready"
          ? "Función preparada. Prepararla no guarda ni publica el borrador."
          : "No se confirmó la preparación. El borrador se conserva; consulta Ajustes o reintenta.",
      );
    } catch (reason) {
      if (!scope.active) return;
      setNotice((reason as Error).message);
    }
  };
  let content;
  if (section === "library")
    content = (
      <LibraryPage context={context} navigate={navigate} search={url.search} />
    );
  else if (section === "sources" && identity === "new")
    content = (
      <NewSourcePage
        key={context.library_id}
        context={context}
        navigate={navigate}
        search={url.search}
      />
    );
  else if (section === "sources")
    content = (
      <SourcePage
        key={identity}
        sourceId={identity}
        context={context}
        navigate={navigate}
      />
    );
  else if (section === "notes")
    content = identity ? (
      <SavedNotePage
        key={identity + url.search}
        noteId={identity}
        context={context}
        navigate={navigate}
        notify={setNotice}
        preferSaved={url.searchParams.get("version") === "server"}
      />
    ) : (
      <NotesPage context={context} navigate={navigate} search={url.search} />
    );
  else if (section === "write")
    content = (
      <WritePage
        context={context}
        navigate={navigate}
        search={url.search}
        notify={setNotice}
      />
    );
  else if (section === "concepts" && identity === "new")
    content = (
      <ConceptEditorPage
        key={context.library_id + url.search}
        context={context}
        navigate={navigate}
        search={url.search}
      />
    );
  else if (section === "concepts" && parts[2] === "edit")
    content = (
      <ConceptEditorPage
        key={context.library_id + parts[1]}
        context={context}
        navigate={navigate}
        search={url.search}
        conceptKey={parts[1]}
      />
    );
  else if (section === "concepts")
    content = identity ? (
      <ConceptPage
        conceptKey={identity}
        context={context}
        navigate={navigate}
      />
    ) : (
      <ConceptsPage
        key={url.search}
        context={context}
        navigate={navigate}
        search={url.search}
      />
    );
  else if (section === "spaces")
    content = (
      <SpacesPage context={context} navigate={navigate} search={url.search} />
    );
  else if (section === "read")
    content = (
      <section>
        <StudyLink to="/study/library" navigate={navigate}>
          Volver a Biblioteca
        </StudyLink>
        <ReadingPage
          key={identity}
          context={context}
          documentId={identity}
          page={Number(url.searchParams.get("page")) || undefined}
          onCreateNote={(metadata, passage) => {
            const draft = newStudyDraft(
              metadata.source.source_id,
              metadata,
              passage,
            );
            studyVault(context.library_id).put(draft);
            navigate("/study/write?draft=" + encodeURIComponent(draft.id!));
          }}
        />
      </section>
    );
  else if (section === "settings" && identity === "appearance")
    content = <AppearancePage />;
  else if (section === "settings")
    content = (
      <section>
        <h1>Ajustes</h1>
        <h2>Biblioteca activa</h2>
        <StudyLink to="/study/settings/appearance" navigate={navigate}>
          Ver los tipos matemáticos y su paleta
        </StudyLink>
        <p>{context.name}</p>
        <p>
          La conexión se configura en el backend local. Las credenciales
          permanecen en el servidor.
        </p>
        <h2>Funciones disponibles</h2>
        <p>
          {context.preparation.notes_ready
            ? "Notas y subrayados preparados."
            : "Guardar notas y subrayados requiere preparación o comprobación."}
        </p>
        <button onClick={() => setRetry((value) => value + 1)}>
          Volver a comprobar
        </button>
        <details>
          <summary>Diagnóstico</summary>
          <p>
            Estado de preparación: {context.preparation.state}. Motivo:{" "}
            {context.preparation.reason || "Sin conflicto detectado"}.
          </p>
          <p>
            El seguimiento de calidad se consulta en los informes locales de
            auditoría. Este diagnóstico comprueba la biblioteca; no consulta el
            estado de SonarQube.
          </p>
        </details>
      </section>
    );
  else if (section === "notebook")
    content = (
      <NotebookPages
        context={context}
        identity={identity}
        navigate={navigate}
        search={url.search}
      />
    );
  else
    content = (
      <section className="study-home">
        <p className="eyebrow">Tu espacio de estudio</p>
        <h1>Leer, escribir, conectar</h1>
        <p>
          Continúa una lectura, recupera tu escritura o vuelve a tus esferas.
        </p>
        <div className="study-home-actions">
          <StudyLink to="/study/library" navigate={navigate}>
            Abrir Biblioteca
          </StudyLink>
          <StudyLink to="/study/notes" navigate={navigate}>
            Recuperar notas y borradores
          </StudyLink>
          <StudyLink to="/study/spaces" navigate={navigate}>
            Volver a Espacios
          </StudyLink>
        </div>
      </section>
    );
  return (
    <div className="study-app">
      <aside className="study-navigation">
        <a
          href="/study"
          onClick={(event) => {
            event.preventDefault();
            navigate("/study");
          }}
          className="study-brand"
        >
          Σ MathMongo
        </a>
        <p className="study-library-label">Biblioteca · {context.name}</p>
        <nav aria-label="Navegación principal">
          {pages.map(([label, path]) => (
            <div
              key={label}
              aria-current={section === path.slice(1) ? "page" : undefined}
            >
              <StudyLink to={"/study" + path} navigate={navigate}>
                {label}
              </StudyLink>
            </div>
          ))}
        </nav>
      </aside>
      <main className="study-main">
        {notice && (
          <p className="study-notice" role="status">
            {notice}
          </p>
        )}
        {context.preparation.state !== "ready" && (
          <aside className="study-preparation">
            <p>
              {context.preparation.state === "pending"
                ? "Puedes leer y escribir borradores. Para guardar notas y subrayados, prepara esta biblioteca."
                : context.preparation.state === "incompatible"
                  ? "La configuración requiere revisión. No se borrarán ni migrarán datos desde esta acción."
                  : "No se pudo comprobar la preparación. Comprueba conexión y permisos; esto no significa que falten índices."}
            </p>
            {context.preparation.state === "pending" ? (
              <>
                <p>
                  Sólo se crean los índices aprobados que faltan. No se borran
                  datos ni se publica el borrador.
                </p>
                <button onClick={() => void prepare()}>
                  Preparar notas y subrayados
                </button>
              </>
            ) : (
              <button onClick={() => setRetry((value) => value + 1)}>
                Volver a comprobar
              </button>
            )}
            <StudyLink to="/study/settings" navigate={navigate}>
              Abrir Ajustes
            </StudyLink>
          </aside>
        )}
        <Suspense
          key={context.library_id + context.runtime_id}
          fallback={<p role="status">Abriendo el espacio de trabajo…</p>}
        >
          {content}
        </Suspense>
      </main>
    </div>
  );
}
