/** Search every associated reference without loading full BibTeX records. */
import { useState } from "react";
import type { StudyContext, Page } from "./api";
import { useStudyResource } from "./navigation";
type Choice = { reference_id: string; title: string; status: string };
export function ReferencePicker({
  context,
  sourceId,
  value,
  changed,
}: {
  context: StudyContext;
  sourceId: string;
  value: string;
  changed: (value: string) => void;
}) {
  const [query, setQuery] = useState(""),
    [page, setPage] = useState(1);
  const list = useStudyResource<Page<Choice>>(
    context,
    "/sources/" +
      encodeURIComponent(sourceId) +
      "/references?" +
      new URLSearchParams({ q: query, page: String(page) }),
  );
  return (
    <div>
      <label>
        Buscar referencia asociada
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
        Referencia bibliográfica
        <select value={value} onChange={(event) => changed(event.target.value)}>
          <option value="">Sin referencia</option>
          {value &&
            !list.data?.items.some((item) => item.reference_id === value) && (
              <option value={value}>Referencia actual conservada</option>
            )}
          {list.data?.items.map((item) => (
            <option
              key={item.reference_id}
              value={item.reference_id}
              disabled={item.status === "archived"}
            >
              {item.title}
              {item.status === "archived" ? " (archivada)" : ""}
            </option>
          ))}
        </select>
      </label>
      {page > 1 && (
        <button type="button" onClick={() => setPage(page - 1)}>
          Referencias anteriores
        </button>
      )}
      {list.data && page * 20 < list.data.total && (
        <button type="button" onClick={() => setPage(page + 1)}>
          Más referencias
        </button>
      )}
      {list.error && (
        <p role="alert">
          {list.error}
          <button type="button" onClick={list.retry}>
            Reintentar referencias
          </button>
        </p>
      )}
    </div>
  );
}
