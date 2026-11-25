/** Existing local draft persistence and scoped HTTP saves, shared by curated Cuaderno forms. */
import { useState } from "react";
import { studyRequest, type StudyContext } from "./api";
import { useLocalForm } from "./useLocalForm";
import { useOperationScope } from "./useOperationScope";
import { type Navigate } from "./navigation";
import {
  activityFields,
  activityNames,
  activityPayload,
  activityValues,
  type ActivityKind,
  type ActivityRecord,
} from "./activity-fields";
export function ActivityWorkspace({
  context,
  kind,
  record,
  navigate,
}: {
  context: StudyContext;
  kind: ActivityKind;
  record?: ActivityRecord;
  navigate: Navigate;
}) {
  const form = useLocalForm(
      `mathmongo-activity-v1:${context.library_id}:${kind}:${record?.id || "new"}`,
      () => ({
        request_id: crypto.randomUUID(),
        revision: record?.revision || "",
        values: activityValues(kind, record),
      }),
    ),
    scope = useOperationScope(context);
  const [busy, setBusy] = useState(false),
    [message, setMessage] = useState("");
  const set = (key: string, value: string) =>
    form.set({ ...form.state, values: { ...form.state.values, [key]: value } });
  const save = async () => {
    setBusy(true);
    setMessage("");
    try {
      const result = await studyRequest<ActivityRecord>(
        "/activities/" +
          kind +
          (record ? "/" + encodeURIComponent(record.id) : ""),
        context,
        {
          request_id: form.state.request_id,
          revision: form.state.revision || null,
          fields: activityPayload(kind, form.state.values),
        },
      );
      if (!scope.active) return;
      form.clear();
      navigate(
        "/study/notebook/" +
          kind +
          "/" +
          encodeURIComponent(result.id) +
          "?saved=" +
          result.revision,
      );
    } catch (reason) {
      if (scope.active) setMessage((reason as Error).message);
    } finally {
      if (scope.active) setBusy(false);
    }
  };
  return (
    <section className="activity-workspace">
      <h2>
        {record ? "Editar" : "Crear"} {activityNames[kind]}
      </h2>
      <p>
        El borrador queda en este navegador. Guardar confirma el registro en la
        biblioteca activa.
      </p>
      <form
        onSubmit={(event) => {
          event.preventDefault();
          void save();
        }}
      >
        <fieldset disabled={busy}>
          <div className="activity-fields">
            {activityFields[kind].map((field) => (
              <label key={field.key}>
                {field.label}
                {field.options ? (
                  <select
                    aria-label={field.label}
                    value={form.state.values[field.key]}
                    onChange={(event) => set(field.key, event.target.value)}
                  >
                    {field.options.map((value) => (
                      <option key={value}>{value}</option>
                    ))}
                  </select>
                ) : field.type === "lines" ? (
                  <textarea
                    aria-label={field.label}
                    value={form.state.values[field.key]}
                    onChange={(event) => set(field.key, event.target.value)}
                  />
                ) : field.type === "checkbox" ? (
                  <input
                    aria-label={field.label}
                    type="checkbox"
                    checked={form.state.values[field.key] === "true"}
                    onChange={(event) =>
                      set(field.key, String(event.target.checked))
                    }
                  />
                ) : (
                  <input
                    aria-label={field.label}
                    type={
                      field.type === "date"
                        ? "date"
                        : field.type === "number"
                          ? "number"
                          : "text"
                    }
                    min={field.type === "number" ? 0 : undefined}
                    step={field.type === "number" ? "any" : undefined}
                    required={field.required}
                    disabled={
                      !!record &&
                      kind === "weekly" &&
                      ["iso_year", "iso_week"].includes(field.key)
                    }
                    value={form.state.values[field.key] ?? ""}
                    onChange={(event) => set(field.key, event.target.value)}
                  />
                )}
              </label>
            ))}
          </div>
          <button className="primary-button" type="submit">
            {busy ? "Confirmando…" : "Guardar " + activityNames[kind]}
          </button>
        </fieldset>
      </form>
      {message && <p role="alert">{message}</p>}
      {form.problem && <p role="alert">{form.problem}</p>}
      <button onClick={form.download}>Descargar borrador</button>
      {form.problem && (
        <button onClick={form.restart}>
          Conservar copia y empezar otro borrador
        </button>
      )}
    </section>
  );
}
