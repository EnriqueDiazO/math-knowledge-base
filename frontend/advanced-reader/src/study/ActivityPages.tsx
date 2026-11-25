/** Bounded task activities and Kanban over the same persisted Backlog; no second task model. */
import { useState } from "react";
import {
  type Page,
  type StudyContext,
  downloadDocument,
  studyBinary,
  studyRequest,
} from "./api";
import { type Navigate, useStudyResource } from "./navigation";
import { StudyLink } from "./StudyLink";
import { NotebookNavigation } from "./NotebookNavigation";
import { ActivityWorkspace } from "./ActivityWorkspace";
import {
  activityNames,
  activityPayload,
  activityTitle,
  activityValues,
  type ActivityKind,
  type ActivityRecord,
} from "./activity-fields";
import { useOperationScope } from "./useOperationScope";
import "./notebook-activities.css";
export function ActivityPages({
  context,
  navigate,
  kind,
  identity,
  search,
  kanban = false,
}: {
  context: StudyContext;
  navigate: Navigate;
  kind: ActivityKind;
  identity: string;
  search: string;
  kanban?: boolean;
}) {
  return (
    <section>
      <p className="eyebrow">Cuaderno · planificación y seguimiento</p>
      <h1>{kanban ? "Kanban" : activityNames[kind]}</h1>
      <NotebookNavigation navigate={navigate} />
      {!context.capabilities?.includes("notebook-activities") ? (
        <p role="status">
          Este servidor todavía no ofrece estas operaciones. Continúa en
          Cuaderno de Streamlit o inicia el backend actualizado; no se
          modificaron tus registros.
        </p>
      ) : identity === "new" ? (
        <ActivityWorkspace context={context} kind={kind} navigate={navigate} />
      ) : identity ? (
        <ActivityDetail
          key={identity + search}
          {...{ context, navigate, kind, identity, search }}
        />
      ) : (
        <ActivityList
          key={search + kind + kanban}
          {...{ context, navigate, kind, search, kanban }}
        />
      )}
    </section>
  );
}
function ActivityDetail({
  context,
  navigate,
  kind,
  identity,
  search,
}: {
  context: StudyContext;
  navigate: Navigate;
  kind: ActivityKind;
  identity: string;
  search: string;
}) {
  const resource = useStudyResource<ActivityRecord>(
    context,
    "/activities/" + kind + "/" + encodeURIComponent(identity),
  );
  return (
    <>
      <StudyLink to={"/study/notebook/" + kind} navigate={navigate}>
        Volver a {activityNames[kind]}
      </StudyLink>
      {new URLSearchParams(search).get("saved") === resource.data?.revision &&
        resource.data && <p role="status">Versión recuperada del servidor.</p>}
      {resource.data?.metrics_at_save && (
        <p>
          Métricas automáticas al último guardado:{" "}
          {resource.data.metrics_at_save.real_hours ?? "no disponibles"} horas ·{" "}
          {resource.data.metrics_at_save.tasks_done ?? "no disponibles"} tareas
          terminadas. Los valores manuales se conservan por separado.
        </p>
      )}
      {resource.error ? (
        <p role="alert">
          {resource.error}
          <button onClick={resource.retry}>Volver a abrir</button>
        </p>
      ) : resource.data ? (
        <ActivityWorkspace
          key={resource.data.revision}
          context={context}
          kind={kind}
          record={resource.data}
          navigate={navigate}
        />
      ) : (
        <p role="status">Abriendo registro…</p>
      )}
    </>
  );
}
function ActivityList({
  context,
  navigate,
  kind,
  search,
  kanban,
}: {
  context: StudyContext;
  navigate: Navigate;
  kind: ActivityKind;
  search: string;
  kanban: boolean;
}) {
  const params = new URLSearchParams(search),
    page = Math.max(1, Number(params.get("page")) || 1),
    query = new URLSearchParams({
      q: params.get("q") || "",
      project: params.get("project") || "",
      status: params.get("status") || "",
      page: String(page),
    });
  const resource = useStudyResource<Page<ActivityRecord>>(
      context,
      "/activities/" + kind + "?" + query,
    ),
    [selected, setSelected] = useState<string[]>([]),
    [problem, setProblem] = useState(""),
    [pending, setPending] = useState(false),
    scope = useOperationScope(context),
    base = "/study/notebook/" + (kanban ? "kanban" : kind);
  const exportSelection = async () => {
    try {
      const blob = await studyBinary(
        "/activities/" + kind + "/export",
        context,
        { ids: selected },
      );
      if (scope.active) downloadDocument(blob, "mathmongo-" + kind + ".csv");
    } catch (reason) {
      if (scope.active) setProblem((reason as Error).message);
    }
  };
  const move = async (record: ActivityRecord, status: string) => {
    setPending(true);
    setProblem("");
    try {
      await studyRequest(
        "/activities/backlog/" + encodeURIComponent(record.id),
        context,
        {
          request_id: crypto.randomUUID(),
          revision: record.revision,
          fields: {
            ...activityPayload("backlog", activityValues("backlog", record)),
            status,
          },
        },
      );
      if (scope.active) resource.retry();
    } catch (reason) {
      if (scope.active) setProblem((reason as Error).message);
    } finally {
      if (scope.active) setPending(false);
    }
  };
  const card = (record: ActivityRecord) => (
    <article key={record.id}>
      <label>
        <input
          type="checkbox"
          checked={selected.includes(record.id)}
          onChange={(event) =>
            setSelected(
              event.target.checked
                ? [...selected, record.id]
                : selected.filter((id) => id !== record.id),
            )
          }
        />
        Seleccionar {activityTitle(record)}
      </label>
      <h3>
        <StudyLink
          to={"/study/notebook/" + kind + "/" + encodeURIComponent(record.id)}
          navigate={navigate}
        >
          {activityTitle(record)}
        </StudyLink>
      </h3>
      <p>
        {String(record.fields.project || "")} ·{" "}
        {String(record.fields.status || record.fields.date || "")}
      </p>
      {kanban && (
        <form
          onSubmit={(event) => {
            event.preventDefault();
            void move(
              record,
              String(new FormData(event.currentTarget).get("status")),
            );
          }}
        >
          <label>
            Estado de {activityTitle(record)}
            <select name="status" defaultValue={String(record.fields.status)}>
              {["Todo", "Doing", "Done", "Blocked", "Canceled"].map(
                (status) => (
                  <option key={status}>{status}</option>
                ),
              )}
            </select>
          </label>
          <button disabled={pending}>Aplicar estado</button>
        </form>
      )}
    </article>
  );
  return (
    <>
      <StudyLink
        className="primary-button"
        to={"/study/notebook/" + kind + "/new"}
        navigate={navigate}
      >
        Crear {activityNames[kind]}
      </StudyLink>
      <form
        onSubmit={(event) => {
          event.preventDefault();
          const data = new FormData(event.currentTarget);
          navigate(
            base +
              "?" +
              new URLSearchParams({
                q: String(data.get("q") || ""),
                project: String(data.get("project") || ""),
                status: String(data.get("status") || ""),
              }),
          );
        }}
      >
        <label>
          Buscar tareas o entregables
          <input name="q" defaultValue={query.get("q") || ""} />
        </label>
        {kind !== "weekly" && (
          <label>
            Proyecto
            <input name="project" defaultValue={query.get("project") || ""} />
          </label>
        )}
        {["worklog", "backlog"].includes(kind) && (
          <label>
            Estado
            <input name="status" defaultValue={query.get("status") || ""} />
          </label>
        )}
        <button>Buscar registros</button>
      </form>
      {resource.error && (
        <p role="alert">
          {resource.error}
          <button onClick={resource.retry}>Reintentar consulta</button>
        </p>
      )}
      {problem && <p role="alert">{problem}</p>}
      {resource.data && (
        <>
          <p>
            {resource.data.total} registros · página {page}.{" "}
            {kanban &&
              "Las columnas muestran esta página del Backlog, incluidos los cancelados."}
          </p>
          {kanban ? (
            <div className="kanban-columns">
              {["Todo", "Doing", "Done", "Blocked", "Canceled"].map(
                (status) => (
                  <section key={status}>
                    <h2>{status}</h2>
                    {resource.data?.items
                      .filter((record) => record.fields.status === status)
                      .map(card)}
                  </section>
                ),
              )}
            </div>
          ) : (
            <div className="activity-records">
              {resource.data.items.map(card)}
            </div>
          )}
          <button
            disabled={!selected.length}
            onClick={() => void exportSelection()}
          >
            Exportar selección CSV
          </button>
          <nav aria-label="Páginas de actividades">
            <button
              disabled={page === 1}
              onClick={() => {
                query.set("page", String(page - 1));
                navigate(base + "?" + query);
              }}
            >
              Anterior
            </button>
            <button
              disabled={page * 20 >= resource.data.total}
              onClick={() => {
                query.set("page", String(page + 1));
                navigate(base + "?" + query);
              }}
            >
              Siguiente
            </button>
          </nav>
        </>
      )}
    </>
  );
}
