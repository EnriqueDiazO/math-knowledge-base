/** Stable activity navigation, with presentation controls separate from mathematical types. */
import type { StudyContext } from "./api";
import type { Navigate } from "./navigation";
import { StudyLink } from "./StudyLink";
import { useInterfacePreferences } from "./interface-preferences";
const groups = [
  {
    label: "Estudio",
    links: [
      ["Inicio", "", "⌂"],
      ["Biblioteca", "library", "▤"],
      ["Documentos y lectura", "library?activity=documents", "▧"],
      ["Notas", "notes", "✎"],
    ],
  },
  {
    label: "Conocimiento",
    links: [
      ["Conceptos", "concepts", "Σ"],
      ["Nuevo concepto", "concepts/new", "+"],
      ["Espacios", "spaces", "◉"],
      ["Relaciones", "spaces?activity=relations", "↔"],
      ["Exportar conceptos", "concepts?activity=export", "↓"],
    ],
  },
  {
    label: "Cuaderno",
    links: [
      ["Cuaderno", "notebook", "▣"],
      ["Diario", "notebook?view=search", "✍"],
      ["Worklog", "notebook/worklog", "◷"],
      ["Backlog", "notebook/backlog", "☷"],
      ["Weekly Review", "notebook/weekly", "▦"],
      ["Deliverables", "notebook/deliverables", "✓"],
      ["Kanban", "notebook/kanban", "▥"],
      ["Cornell", "notebook/cornell", "C"],
      ["CPI", "notebook/cpi", "CPI"],
    ],
  },
  {
    label: "Administración",
    links: [
      ["Añadir fuente", "sources/new", "+"],
      ["Ajustes", "settings", "⚙"],
      ["Diagnóstico", "settings?section=diagnostic", "ⓘ"],
    ],
  },
] as const;
const pages = groups.flatMap((group) => [...group.links]);
export function StudyNavigation({
  context,
  navigate,
}: {
  context: StudyContext;
  section: string;
  navigate: Navigate;
}) {
  const { preferences, change } = useInterfacePreferences();
  return (
    <aside className="study-navigation">
      <div className="study-brand-row">
        <StudyLink to="/study" navigate={navigate} className="study-brand">
          Σ <span className="navigation-label">MathMongo</span>
        </StudyLink>
        <button
          aria-label={
            preferences.navigationCollapsed
              ? "Mostrar navegación"
              : "Ocultar navegación"
          }
          aria-expanded={!preferences.navigationCollapsed}
          onClick={() =>
            change({ navigationCollapsed: !preferences.navigationCollapsed })
          }
        >
          {preferences.navigationCollapsed ? "›" : "‹"}
        </button>
      </div>
      <p className="study-library-label navigation-label">
        Tu biblioteca de estudio
      </p>
      <nav aria-label="Navegación principal">
        {groups.map((group) => (
          <details className="navigation-group" key={group.label} open>
            <summary>
              <span className="navigation-label">{group.label}</span>
            </summary>
            {group.links.map(([label, path, symbol]) => (
              <div
                key={label}
                aria-current={
                  location.pathname ===
                    "/study" + (path ? "/" + path.split("?")[0] : "") &&
                  (path.includes("?")
                    ? location.search === "?" + path.split("?")[1]
                    : !location.search ||
                      (!location.search.includes("activity=") &&
                        !location.search.includes("section=")))
                    ? "page"
                    : undefined
                }
              >
                <StudyLink
                  to={"/study" + (path ? "/" + path : "")}
                  navigate={navigate}
                >
                  <span className="navigation-symbol" aria-hidden="true">
                    {symbol}
                  </span>
                  <span className="navigation-label">{label}</span>
                </StudyLink>
              </div>
            ))}
          </details>
        ))}
      </nav>
      <div className="navigation-foot navigation-label">
        <p>Biblioteca activa</p>
        <strong title={context.name}>{context.name}</strong>
        <StudyLink to="/study/settings" navigate={navigate}>
          Conexión y ajustes
        </StudyLink>
      </div>
    </aside>
  );
}
export function StudyTopbar({
  context,
  section,
  navigate,
}: {
  context: StudyContext;
  section: string;
  navigate: Navigate;
}) {
  const { preferences, change, problem } = useInterfacePreferences(),
    label = pages.find((p) => p[1] === section)?.[0] || "Estudio";
  return (
    <header className="study-topbar">
      <nav aria-label="Ruta de estudio">
        <StudyLink to="/study" navigate={navigate}>
          Estudio
        </StudyLink>
        <span aria-hidden="true"> / </span>
        <span>{label}</span>
      </nav>
      <div className="study-global-controls">
        <StudyLink
          to="/study/settings"
          navigate={navigate}
          className="connection-badge"
        >
          Biblioteca: {context.name}
        </StudyLink>
        <div
          className="segmented-control"
          role="group"
          aria-label="Tema de la aplicación"
        >
          <button
            aria-pressed={preferences.theme === "light"}
            onClick={() => change({ theme: "light" })}
          >
            Claro
          </button>
          <button
            aria-pressed={preferences.theme === "dark"}
            onClick={() => change({ theme: "dark" })}
          >
            Oscuro
          </button>
        </div>
      </div>
      {problem && <p role="status">{problem}</p>}
    </header>
  );
}
