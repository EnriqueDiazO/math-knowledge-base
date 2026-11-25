/** Recognizable notebook activities, preserving Cornell and CPI as distinct tools. */
import { StudyLink } from "./StudyLink";
import type { Navigate } from "./navigation";
const notebookActivities = [
  ["Worklog", "worklog"],
  ["Backlog", "backlog"],
  ["Weekly Review", "weekly"],
  ["Deliverables", "deliverables"],
  ["Kanban", "kanban"],
  ["Diario", ""],
  ["Cornell", "cornell"],
  ["CPI", "cpi"],
] as const;
export function NotebookNavigation({ navigate }: { navigate: Navigate }) {
  return (
    <nav className="notebook-navigation" aria-label="Actividades de Cuaderno">
      {notebookActivities.map(([label, path]) => (
        <StudyLink
          key={label}
          to={"/study/notebook" + (path ? "/" + path : "")}
          navigate={navigate}
        >
          {label}
        </StudyLink>
      ))}
    </nav>
  );
}
