import { useEffect, useRef, useState } from "react";
import renderMap from "../knowledge-map/component";
import type { Data, Intent } from "../knowledge-map/model";
import { DocumentContent } from "./DocumentSurface";
import { executeStudy } from "./api";
import type { ConceptDetail, StudyContext } from "./api";
import { useStudyResource } from "./navigation";
import { StudyLink } from "./StudyLink";
import type { Navigate } from "./navigation";

export function ConceptsPage({
  context,
  navigate,
}: {
  context: StudyContext;
  navigate: Navigate;
}) {
  const resource = useStudyResource<Data>(context, "/overview");
  const [query, setQuery] = useState("");
  return (
    <section>
      <header>
        <p className="eyebrow">Conocimiento compartido</p>
        <h1>Conceptos</h1>
        <p>
          Lee un concepto y sigue su procedencia. Las esferas muestran los
          mismos conceptos.
        </p>
      </header>
      <label>
        Buscar conceptos
        <input
          type="search"
          value={query}
          onChange={(event) => setQuery(event.target.value)}
        />
      </label>
      {resource.error && (
        <p role="alert">
          {resource.error} <button onClick={resource.retry}>Reintentar</button>
        </p>
      )}
      {resource.data?.nodes
        .filter((node) =>
          node.titulo.toLocaleLowerCase().includes(query.toLocaleLowerCase()),
        )
        .map((node) => (
          <article key={node.key}>
            <h2>
              <StudyLink
                to={"/study/concepts/" + encodeURIComponent(node.key)}
                navigate={navigate}
              >
                {node.titulo}
              </StudyLink>
            </h2>
            <p>
              {node.tipo} · {node.source}
            </p>
          </article>
        ))}
    </section>
  );
}
export function ConceptPage({
  context,
  conceptKey,
  navigate,
}: {
  context: StudyContext;
  conceptKey: string;
  navigate: Navigate;
}) {
  const resource = useStudyResource<ConceptDetail>(
    context,
    "/concepts/detail?" + new URLSearchParams({ key: conceptKey }),
  );
  if (resource.error)
    return (
      <p role="alert">
        {resource.error} <button onClick={resource.retry}>Reintentar</button>
      </p>
    );
  const concept = resource.data;
  if (!concept) return <p role="status">Abriendo el concepto…</p>;
  return (
    <section>
      <StudyLink to="/study/concepts" navigate={navigate}>
        Volver a Conceptos
      </StudyLink>
      <header>
        <p className="eyebrow">
          {concept.tipo} · {concept.source}
        </p>
        <h1>{concept.titulo}</h1>
        <StudyLink
          to={"/study/spaces?concept=" + encodeURIComponent(concept.key)}
          navigate={navigate}
        >
          Ver en una esfera
        </StudyLink>
      </header>
      <DocumentContent content={concept.contenido_latex} />
      <section>
        <h2>Origen y pasajes</h2>
        {concept.passages.map((passage, index) => (
          <article key={index}>
            {passage.quote && <blockquote>{passage.quote}</blockquote>}
            <StudyLink
              to={
                "/study/read/" +
                encodeURIComponent(passage.document_id) +
                "?" +
                new URLSearchParams({
                  page: String(passage.pdf_page ?? 1),
                  ...(passage.annotation_id
                    ? { annotation: passage.annotation_id }
                    : {}),
                })
              }
              navigate={navigate}
            >
              Volver al pasaje original
              {passage.pdf_page ? " · página PDF " + passage.pdf_page : ""}
            </StudyLink>
          </article>
        ))}
        {!concept.passages.length && (
          <p>
            Este concepto no tiene un pasaje vinculado. Su fuente histórica se
            conserva.
          </p>
        )}
      </section>
    </section>
  );
}
export function SpacesPage({
  context,
  navigate,
  search,
}: {
  context: StudyContext;
  navigate: Navigate;
  search: string;
}) {
  const resource = useStudyResource<Data>(context, "/overview");
  const host = useRef<HTMLDivElement>(null);
  const [message, setMessage] = useState("");
  const navigateRef = useRef(navigate);
  useEffect(() => {
    navigateRef.current = navigate;
  }, [navigate]);
  useEffect(() => {
    if (!host.current || !resource.data) return;
    let disposed = false,
      cleanup = () => {};
    const container = host.current;
    const mount = (data: Data) => {
      cleanup();
      cleanup = renderMap({
        parentElement: container,
        data,
        selectionKey: new URLSearchParams(search).get("concept") ?? undefined,
        onOpenDocument: (key) =>
          navigateRef.current("/study/concepts/" + encodeURIComponent(key)),
        setTriggerValue: (key, value) => {
          if (key === "open_note") {
            navigateRef.current(
              "/study/concepts/" +
                encodeURIComponent((value as { key: string }).key),
            );
            return;
          }
          if (key !== "intent") {
            setMessage(
              "Esta acción se incorporará en el siguiente lote. Tu disposición y borrador se conservan.",
            );
            return;
          }
          const intent = value as Intent;
          void executeStudy(context, intent)
            .then((result) => {
              if (!disposed) {
                setMessage(result.message);
                mount({ ...data, result });
              }
            })
            .catch((reason) => {
              if (!disposed) setMessage(reason.message);
            });
        },
      });
    };
    mount(resource.data);
    return () => {
      disposed = true;
      cleanup();
    };
  }, [resource.data, search, context]);
  return (
    <section>
      <header>
        <p className="eyebrow">Espacios de estudio</p>
        <h1>Esferas de conocimiento</h1>
        <p>
          Organiza y relaciona conceptos compartidos; abre su lectura sin copiar
          el contenido.
        </p>
      </header>
      {resource.error && (
        <p role="alert">
          {resource.error} <button onClick={resource.retry}>Reintentar</button>
        </p>
      )}
      <p role="status">{message}</p>
      <div ref={host} className="study-sphere" />
    </section>
  );
}
