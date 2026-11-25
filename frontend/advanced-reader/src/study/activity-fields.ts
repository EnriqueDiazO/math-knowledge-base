/** Curated task forms matching Cuaderno contracts; never infer UI from arbitrary Mongo records. */
export type ActivityKind = "worklog" | "backlog" | "weekly" | "deliverables";
export type ActivityField = {
  key: string;
  label: string;
  type?: "date" | "number" | "lines" | "tags" | "checkbox";
  options?: string[];
  required?: boolean;
  initial?: string;
};
const project = { key: "project", label: "Proyecto", required: true },
  task = { key: "task", label: "Tarea", required: true },
  tags: ActivityField = {
    key: "tags",
    label: "Etiquetas separadas por comas",
    type: "tags",
  };
export const activityNames: Record<ActivityKind, string> = {
  worklog: "Worklog",
  backlog: "Backlog",
  weekly: "Weekly Review",
  deliverables: "Deliverables",
};
export const activityFields: Record<ActivityKind, ActivityField[]> = {
  worklog: [
    { key: "date", label: "Fecha", type: "date", required: true },
    { key: "block", label: "Bloque", options: ["AM", "PM", "Noche"] },
    { key: "hours", label: "Horas", type: "number", initial: "0" },
    {
      key: "status",
      label: "Estado",
      options: [
        "Planificado",
        "En progreso",
        "Hecho",
        "Bloqueado",
        "Cancelado",
      ],
    },
    project,
    { key: "module", label: "Módulo" },
    task,
    {
      key: "description_evidence",
      label: "Descripción y evidencia",
      type: "lines",
    },
    { key: "evidence_url", label: "Enlace o ruta de evidencia" },
    { key: "next_step", label: "Siguiente paso" },
    tags,
  ],
  backlog: [
    project,
    { key: "module", label: "Módulo" },
    task,
    { key: "owner", label: "Responsable", required: true },
    { key: "description", label: "Descripción", type: "lines" },
    { key: "priority", label: "Prioridad", options: ["Media", "Alta", "Baja"] },
    {
      key: "status",
      label: "Estado",
      options: ["Todo", "Doing", "Done", "Blocked", "Canceled"],
    },
    { key: "estimate_hours", label: "Horas estimadas", type: "number" },
    { key: "target_date", label: "Fecha objetivo", type: "date" },
    tags,
  ],
  deliverables: [
    { key: "date", label: "Fecha", type: "date", required: true },
    project,
    { key: "deliverable", label: "Nombre del entregable", required: true },
    {
      key: "type",
      label: "Tipo",
      options: [
        "reporte",
        "codigo",
        "dataset",
        "presentacion",
        "evidencia",
        "otro",
      ],
    },
    { key: "url_or_path", label: "Ruta o URL", required: true },
    { key: "commit_ref", label: "Referencia de commit" },
    { key: "notes", label: "Notas", type: "lines" },
    tags,
  ],
  weekly: [
    { key: "iso_year", label: "Año ISO", type: "number", required: true },
    { key: "iso_week", label: "Semana ISO", type: "number", required: true },
    {
      key: "weekly_objectives",
      label: "Objetivos (uno por línea)",
      type: "lines",
    },
    { key: "wins", label: "Logros (uno por línea)", type: "lines" },
    {
      key: "blocks_risks",
      label: "Bloqueos y riesgos (uno por línea)",
      type: "lines",
    },
    {
      key: "plan_next_week",
      label: "Plan siguiente semana (uno por línea)",
      type: "lines",
    },
    {
      key: "manual_override_metrics",
      label: "Usar métricas manuales",
      type: "checkbox",
    },
    {
      key: "manual_real_hours",
      label: "Horas reales manuales",
      type: "number",
    },
    {
      key: "manual_tasks_done",
      label: "Tareas terminadas manuales",
      type: "number",
    },
  ],
};
export type ActivityRecord = {
  id: string;
  revision: string;
  fields: Record<string, unknown>;
  metrics_at_save?: { real_hours: number | null; tasks_done: number | null };
};
export function activityValues(
  kind: ActivityKind,
  record?: ActivityRecord,
): Record<string, string> {
  return Object.fromEntries(
    activityFields[kind].map((field) => {
      const value = record?.fields[field.key];
      return [
        field.key,
        Array.isArray(value)
          ? value.join(field.type === "tags" ? ", " : "\n")
          : value != null
            ? String(value)
            : (field.initial ??
              field.options?.[0] ??
              (field.key === "date"
                ? new Date().toISOString().slice(0, 10)
                : field.key === "iso_year"
                  ? String(new Date().getFullYear())
                  : field.key === "iso_week"
                    ? "1"
                    : "")),
      ];
    }),
  );
}
export function activityPayload(
  kind: ActivityKind,
  values: Record<string, string>,
) {
  return Object.fromEntries(
    activityFields[kind].map((field) => {
      const value = values[field.key] ?? "";
      return [
        field.key,
        field.type === "tags"
          ? value
              .split(",")
              .map((x) => x.trim())
              .filter(Boolean)
          : kind === "weekly" && field.type === "lines"
            ? value
                .split("\n")
                .map((x) => x.trim())
                .filter(Boolean)
            : field.type === "number"
              ? value === ""
                ? null
                : Number(value)
              : field.type === "checkbox"
                ? value === "true"
                : field.type === "date" && value === ""
                  ? null
                  : value,
      ];
    }),
  );
}
export function activityTitle(record: ActivityRecord) {
  return String(
    record.fields.task ||
      record.fields.deliverable ||
      `${record.fields.iso_year} · semana ${record.fields.iso_week}`,
  );
}
