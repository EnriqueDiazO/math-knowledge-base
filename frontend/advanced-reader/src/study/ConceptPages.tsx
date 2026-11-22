import { useEffect, useRef, useState } from "react";
import renderMap from "../knowledge-map/component";
import type { Data, Intent } from "../knowledge-map/model";
import { DocumentContent } from "./DocumentSurface";
import { ConceptTypeBadge } from "./ConceptTypeBadge";
import { executeStudy, getOverview } from "./api";
import type { ConceptDetail, StudyContext, Page } from "./api";
import { conceptTypes } from "../knowledge-map/concept-types";
import { SourcePicker } from "./SourcePicker";
import { ConceptRelations } from "./ConceptRelations";
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
  const [query, setQuery] = useState("");
  const [kind, setKind] = useState(""),
    [source, setSource] = useState(""),
    [page, setPage] = useState(1);
  const resource = useStudyResource<
    Page<{ key: string; titulo: string; tipo: string; source: string }>
  >(
    context,
    "/concepts?" +
      new URLSearchParams({
        q: query,
        tipo: kind,
        source_id: source,
        page: String(page),
      }),
  );
  return (
    <section>
      <header>
        <p className="eyebrow">Conocimiento compartido</p>
        <h1>Conceptos</h1>
        <StudyLink
          to="/study/concepts/new"
          navigate={navigate}
          className="primary-button"
        >
          + Crear concepto
        </StudyLink>
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
          onChange={(event) => {
            setQuery(event.target.value);
            setPage(1);
          }}
        />
      </label>
      <label>
        Explorar por tipo
        <select
          value={kind}
          onChange={(event) => {
            setKind(event.target.value);
            setPage(1);
          }}
        >
          <option value="">Todos los tipos</option>
          {Object.entries(conceptTypes).map(([value, type]) => (
            <option key={value} value={value}>
              {type.label}
            </option>
          ))}
        </select>
      </label>
      <SourcePicker context={context} value={source} allowAll choose={value=>{setSource(value);setPage(1);}}/>
      {resource.error && (
        <p role="alert">
          {resource.error} <button onClick={resource.retry}>Reintentar</button>
        </p>
      )}
      {resource.data?.items.map((node) => (
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
            <ConceptTypeBadge type={node.tipo} /> · {node.source}
          </p>
        </article>
      ))}
      <nav aria-label="Páginas de conceptos">
        <button
          type="button"
          disabled={page === 1}
          onClick={() => setPage(page - 1)}
        >
          Anterior
        </button>
        <button
          type="button"
          disabled={!resource.data || page * 20 >= resource.data.total}
          onClick={() => setPage(page + 1)}
        >
          Siguiente
        </button>
      </nav>
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
          <ConceptTypeBadge type={concept.tipo} /> · {concept.source}
        </p>
        <h1>{concept.titulo}</h1>
        <div className="study-actions">
          <StudyLink
            to={"/study/concepts/" + encodeURIComponent(concept.key) + "/edit"}
            navigate={navigate}
          >
            Editar concepto
          </StudyLink>
          <StudyLink
            to={"/study/sources/" + encodeURIComponent(concept.source_id)}
            navigate={navigate}
          >
            Abrir fuente
          </StudyLink>
        </div>
        <StudyLink
          to={"/study/spaces?concept=" + encodeURIComponent(concept.key)}
          navigate={navigate}
        >
          Ver en una esfera
        </StudyLink>
      </header>
      <DocumentContent content={concept.contenido_latex} />
      <ConceptRelations
        context={context}
        concept={concept}
        navigate={navigate}
        changed={resource.retry}
      />
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
        onOpenDocument: (key, edit) =>
          navigateRef.current(
            "/study/concepts/" +
              encodeURIComponent(key) +
              (edit ? "/edit" : ""),
          ),
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
            .then(async (result) => {
              if (!disposed) {
                setMessage(result.message);
                const fresh =
                  result.status === "saved" ? await getOverview(context) : data;
                if (!disposed) mount({ ...fresh, result });
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
