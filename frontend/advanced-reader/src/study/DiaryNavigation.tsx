/** Diary views retain the same saved identities and shared editor. */
import { StudyLink } from "./StudyLink";
import type { Navigate } from "./navigation";
export function DiaryNavigation({ navigate }: { navigate: Navigate }) {
  return (
    <nav className="notebook-navigation" aria-label="Secciones de Diario">
      <StudyLink to="/study/notebook/new" navigate={navigate}>
        Nueva nota
      </StudyLink>
      {[
        ["Buscar", "search"],
        ["Timeline", "timeline"],
        ["Calendario", "calendar"],
        ["Proyectos", "projects"],
        ["Exportar", "export"],
      ].map(([label, view]) => (
        <StudyLink
          key={view}
          to={"/study/notebook?view=" + view}
          navigate={navigate}
        >
          {label}
        </StudyLink>
      ))}
    </nav>
  );
}
export function DiaryFilters({
  search,
  navigate,
}: {
  search: string;
  navigate: Navigate;
}) {
  const params = new URLSearchParams(search);
  return (
    <form
      onSubmit={(event) => {
        event.preventDefault();
        const values = new FormData(event.currentTarget);
        for (const key of [
          "q",
          "project",
          "context",
          "tags",
          "start_date",
          "end_date",
          "year",
          "month",
        ]) {
          const value = String(values.get(key) || "");
          if (value) params.set(key, value);
          else params.delete(key);
        }
        params.delete("page");
        navigate("/study/notebook?" + params);
      }}
    >
      <div className="activity-fields">
        {[
          ["Buscar en el Cuaderno", "q", "search"],
          ["Filtrar por proyecto", "project", "text"],
          ["Contexto", "context", "text"],
          ["Etiquetas (todas, separadas por comas)", "tags", "text"],
          ["Desde", "start_date", "date"],
          ["Hasta", "end_date", "date"],
          ["Año del calendario", "year", "number"],
          ["Mes del calendario", "month", "number"],
        ].map(([label, key, type]) => (
          <label key={key}>
            {label}
            <input
              name={key}
              type={type}
              min={key === "month" ? 1 : key === "year" ? 1900 : undefined}
              max={key === "month" ? 12 : undefined}
              defaultValue={params.get(key) || ""}
            />
          </label>
        ))}
      </div>
      <button type="submit">Buscar entradas</button>
    </form>
  );
}
