import { useEffect, useRef, useState } from "react";
import renderMap from "../knowledge-map/component";
import type { Data, Intent } from "../knowledge-map/model";
import { ConceptTypeBadge } from "./ConceptTypeBadge";
import { executeStudy, getOverview } from "./api";
import type { StudyContext, Page } from "./api";
import { conceptTypes } from "../knowledge-map/concept-types";
import { SourcePicker } from "./SourcePicker";
import { ExportActions } from "./ExportActions";
import { useStudyResource } from "./navigation";
import { StudyLink } from "./StudyLink";
import type { Navigate } from "./navigation";

export function ConceptsPage({
  context,
  navigate,
  search = "",
}: {
  context: StudyContext;
  navigate: Navigate;
  search?: string;
}) {
  const [query, setQuery] = useState("");
  const [selected, setSelected] = useState<string[]>([]);
  const [kind, setKind] = useState(""),
    [source, setSource] = useState(new URLSearchParams(search).get("source") || ""),
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
        document_id: new URLSearchParams(search).get("document") || "",
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
      <SourcePicker
        context={context}
        value={source}
        allowAll
        choose={(value) => {
          setSource(value);
          setPage(1);
        }}
      />
      {resource.error && (
        <p role="alert">
          {resource.error} <button onClick={resource.retry}>Reintentar</button>
        </p>
      )}
      {resource.data?.items.map((node) => (
        <article key={node.key}>
          <label>
            <input
              type="checkbox"
              checked={selected.includes(node.key)}
              onChange={(e) =>
                setSelected(
                  e.target.checked
                    ? [...selected, node.key]
                    : selected.filter((key) => key !== node.key),
                )
              }
            />
            Seleccionar {node.titulo}
          </label>
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
      {selected.length > 0 && (
        <ExportActions context={context} conceptKeys={selected} />
      )}
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
export { ConceptPage } from "./ConceptReader";
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
