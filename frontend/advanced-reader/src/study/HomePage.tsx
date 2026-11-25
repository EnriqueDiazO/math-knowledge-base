/** Real, bounded recent activity and existing draft recovery, without loading documents. */
import { useEffect, useState } from "react";
import type { StudyContext } from "./api";
import { useStudyResource, type Navigate } from "./navigation";
import { StudyLink } from "./StudyLink";
import {
  recoverableWriting,
  type RecoverableWriting,
} from "./recoverable-writing";
import { bibliographicText } from "./bibliographic-text";
import "./home.css";
type HomeSummary = {
  counts: {
    sources: number;
    concepts: number;
    documents: number;
    notes: number;
  };
  concepts: { key: string; title: string; type: string }[];
  notes: { note_id: string; title: string; family: string }[];
  reading_notes: { note_id: string; title: string }[];
  documents: {
    document_id: string;
    title: string;
    kind: string;
    source_id: string;
  }[];
};
export default function HomePage({
  context,
  navigate,
}: {
  context: StudyContext;
  navigate: Navigate;
}) {
  const supported = context.capabilities?.includes("home-summary") === true;
  const resource = useStudyResource<HomeSummary>(context, "/home", supported);
  const library = context.library_id;
  const [writing, setWriting] = useState<{
    library: string;
    items: RecoverableWriting[];
  }>();
  useEffect(() => {
    let active = true;
    void recoverableWriting(library).then((items) => {
      if (active) setWriting({ library, items });
    });
    return () => {
      active = false;
    };
  }, [library]);
  const drafts = writing?.library === library ? writing.items : null;
  const data = resource.data,
    valid =
      data &&
      data.counts &&
      ["sources", "concepts", "documents", "notes"].every(
        (key) =>
          Number.isInteger(data.counts[key as keyof typeof data.counts]) &&
          data.counts[key as keyof typeof data.counts] >= 0,
      ) &&
      [data.concepts, data.notes, data.reading_notes, data.documents].every(
        Array.isArray,
      );
  return (
    <section className="study-home study-dashboard">
      <header className="home-hero">
        <p className="eyebrow">Tu espacio de estudio</p>
        <h1>Leer, escribir, conectar</h1>
        <p>
          Retoma una idea, continúa una lectura y conserva lo que vas
          comprendiendo.
        </p>
        <div className="study-actions">
          <StudyLink
            to="/study/library"
            navigate={navigate}
            className="primary-button"
          >
            Abrir Biblioteca
          </StudyLink>
          <StudyLink to="/study/notebook" navigate={navigate}>
            Escribir en Cuaderno
          </StudyLink>
          <StudyLink to="/study/concepts/new" navigate={navigate}>
            Crear concepto
          </StudyLink>
        </div>
      </header>
      {(resource.error || (data && !valid)) && (
        <p role="alert">
          {resource.error || "No se pudo interpretar la actividad recibida."}{" "}
          <button onClick={resource.retry}>Reintentar actividad</button>
        </p>
      )}
      {valid && (
        <div
          className="home-indicators"
          aria-label="Contenido de esta biblioteca"
        >
          {(
            [
              ["sources", "Fuentes catalogadas", "/study/library"],
              ["documents", "Documentos", "/study/library"],
              ["concepts", "Conceptos", "/study/concepts"],
              ["notes", "Notas guardadas", "/study/notebook"],
            ] as const
          ).map(([key, label, path]) => (
            <StudyLink to={path} navigate={navigate} key={key}>
              <strong>{data.counts[key]}</strong>
              <span>{label}</span>
            </StudyLink>
          ))}
        </div>
      )}
      <div className="home-columns">
        <section className="workbench-card">
          <header>
            <h2>Continuar escritura</h2>
            <StudyLink to="/study/notes" navigate={navigate}>
              Notas y borradores
            </StudyLink>
          </header>
          {!drafts ? (
            <p>Buscando borradores en este navegador…</p>
          ) : drafts.length ? (
            <ul className="activity-list">
              {drafts.slice(0, 6).map((d) => (
                <li key={d.key}>
                  <StudyLink to={d.path} navigate={navigate}>
                    {d.title}
                  </StudyLink>
                  <small>{d.kind} · Conservado en este navegador</small>
                </li>
              ))}
            </ul>
          ) : (
            <p>No hay escritura local pendiente en esta biblioteca.</p>
          )}
          <StudyLink to="/study/concepts/new" navigate={navigate}>
            Recuperar escritura de conceptos
          </StudyLink>
          <p className="secondary-copy">
            Los borradores locales y las notas guardadas son estados diferentes.
          </p>
        </section>
        <section className="workbench-card">
          <header>
            <h2>Notas para retomar</h2>
            <StudyLink to="/study/notebook" navigate={navigate}>
              Ver Cuaderno
            </StudyLink>
          </header>
          {valid ? (
            <ul className="activity-list">
              {data.notes.map((note) => (
                <li key={note.note_id}>
                  <StudyLink
                    to={
                      "/study/notebook/" +
                      (note.family === "diary" ? "" : note.family + "/") +
                      encodeURIComponent(note.note_id)
                    }
                    navigate={navigate}
                  >
                    {note.title}
                  </StudyLink>
                  <small>
                    {note.family === "diary"
                      ? "Diario"
                      : note.family === "cpi"
                        ? "CPI"
                        : "Cornell"}{" "}
                    · Guardada en la biblioteca
                  </small>
                </li>
              ))}
              {data.reading_notes.map((note) => (
                <li key={note.note_id}>
                  <StudyLink
                    to={"/study/notes/" + encodeURIComponent(note.note_id)}
                    navigate={navigate}
                  >
                    {note.title}
                  </StudyLink>
                  <small>Nota de lectura</small>
                </li>
              ))}
            </ul>
          ) : (
            <p>
              {supported
                ? "Consultando tus notas…"
                : "Abre Cuaderno para consultar tus notas guardadas."}
            </p>
          )}
          {valid && !data.notes.length && !data.reading_notes.length && (
            <p>Todavía no hay notas guardadas.</p>
          )}
        </section>
        <section className="workbench-card">
          <header>
            <h2>Volver a tus conceptos</h2>
            <StudyLink to="/study/concepts" navigate={navigate}>
              Explorar conceptos
            </StudyLink>
          </header>
          {valid && (
            <ul className="activity-list">
              {data.concepts.map((c) => (
                <li key={c.key}>
                  <StudyLink
                    to={"/study/concepts/" + encodeURIComponent(c.key)}
                    navigate={navigate}
                  >
                    {bibliographicText(c.title)}
                  </StudyLink>
                </li>
              ))}
            </ul>
          )}
        </section>
        <section className="workbench-card">
          <header>
            <h2>Continuar lectura</h2>
            <StudyLink to="/study/library" navigate={navigate}>
              Ver documentos
            </StudyLink>
          </header>
          {valid && (
            <ul className="activity-list">
              {data.documents.map((d) => (
                <li key={d.document_id}>
                  <StudyLink
                    to={
                      d.kind === "pdf"
                        ? "/study/read/" + encodeURIComponent(d.document_id)
                        : "/study/sources/" + encodeURIComponent(d.source_id)
                    }
                    navigate={navigate}
                  >
                    {bibliographicText(d.title)}
                  </StudyLink>
                </li>
              ))}
            </ul>
          )}
          {valid && !data.documents.length && (
            <p>
              Añade un documento desde Biblioteca para comenzar una lectura.
            </p>
          )}
          <StudyLink to="/study/spaces" navigate={navigate}>
            Volver a Espacios y relaciones
          </StudyLink>
        </section>
      </div>
    </section>
  );
}
