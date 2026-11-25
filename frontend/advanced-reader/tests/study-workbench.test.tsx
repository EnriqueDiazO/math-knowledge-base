import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import { afterEach, expect, test, vi } from "vitest";
import { ActivityWorkspace } from "../src/study/ActivityWorkspace";
import { activityPayload, activityValues } from "../src/study/activity-fields";
import { InterfacePreferencesProvider } from "../src/study/InterfacePreferencesProvider";
import {
  defaultInterface,
  interfacePreferenceKey,
  readInterfacePreferences,
} from "../src/study/interface-preferences";
import { LibraryPage } from "../src/study/LibraryPages";
import HomePage from "../src/study/HomePage";
import { StudyNavigation } from "../src/study/StudyNavigation";
import { bibliographicText } from "../src/study/bibliographic-text";
import type { StudyContext } from "../src/study/api";
const context: StudyContext = {
  library_id: "owned",
  runtime_id: "run",
  name: "Biblioteca temporal",
  capabilities: ["home-summary", "notebook-activities"],
  preparation: {
    state: "ready",
    reason: "",
    version: "1",
    notes_ready: true,
    reading_ready: true,
  },
};
afterEach(() => {
  cleanup();
  localStorage.clear();
  vi.unstubAllGlobals();
});
function response(value: unknown) {
  return { ok: true, json: async () => value };
}
test("preferences validate values and preserve unrelated canonical drafts", () => {
  localStorage.setItem("draft-original", String.raw`\unknown{x}`);
  localStorage.setItem(interfacePreferenceKey, "broken");
  expect(readInterfacePreferences()).toEqual(defaultInterface);
  localStorage.setItem(
    interfacePreferenceKey,
    JSON.stringify({ theme: "light", libraryView: "list", contextWidth: 9999 }),
  );
  expect(readInterfacePreferences()).toMatchObject({
    theme: "light",
    libraryView: "list",
    contextWidth: 440,
  });
  expect(localStorage.getItem("draft-original")).toBe(String.raw`\unknown{x}`);
});
test("navigation exposes all implemented Cuaderno activities and direct structured editors", () => {
  render(
    <InterfacePreferencesProvider>
      <StudyNavigation
        context={context}
        section="notebook"
        navigate={vi.fn()}
      />
    </InterfacePreferencesProvider>,
  );
  for (const name of [
    "Worklog",
    "Backlog",
    "Weekly Review",
    "Deliverables",
    "Kanban",
    "Diario",
    "Cornell",
    "CPI",
  ])
    expect(screen.getByRole("link", { name }).getAttribute("href")).toContain(
      "/study/notebook",
    );
  expect(
    screen.getByRole("link", { name: "Diagnóstico" }).getAttribute("href"),
  ).toBe("/study/settings?section=diagnostic");
  fireEvent.click(screen.getByRole("button", { name: "Ocultar navegación" }));
  expect(
    JSON.parse(localStorage.getItem(interfacePreferenceKey)!)
      .navigationCollapsed,
  ).toBe(true);
});
test("home requests bounded real summaries and does not confuse unavailable counts with zero", async () => {
  const fetch = vi.fn().mockResolvedValue(
    response({
      counts: { sources: 8, concepts: 9, documents: 2, notes: 3 },
      concepts: [],
      notes: [],
      reading_notes: [],
      documents: [],
    }),
  );
  vi.stubGlobal("fetch", fetch);
  render(<HomePage context={context} navigate={vi.fn()} />);
  await screen.findByText("8");
  expect(fetch.mock.calls[0][0]).toBe("/api/study/v1/home");
  expect(fetch.mock.calls[0][1].headers["X-MathMongo-Library"]).toBe("owned");
});
test("previous running backend without new capabilities receives no unsupported home request", () => {
  const fetch = vi.fn();
  vi.stubGlobal("fetch", fetch);
  render(
    <HomePage
      context={{ ...context, capabilities: undefined }}
      navigate={vi.fn()}
    />,
  );
  expect(fetch).not.toHaveBeenCalled();
  expect(
    screen.getByRole("heading", { name: "Leer, escribir, conectar" }),
  ).toBeTruthy();
});
test("both library layouts retain the same sources, search and actions after preference reload", async () => {
  vi.stubGlobal(
    "fetch",
    vi.fn().mockResolvedValue(
      response({
        items: [
          {
            source_id: "legacy-key",
            name: "Texto",
            source_type: "libro",
            bibliography: [
              {
                title: "Texto",
                authors: [{ literal: "Autora" }],
                year: 1964,
              },
            ],
          },
        ],
        page: 1,
        total: 1,
      }),
    ),
  );
  const view = render(
    <InterfacePreferencesProvider>
      <LibraryPage context={context} search="" navigate={vi.fn()} />
    </InterfacePreferencesProvider>,
  );
  await screen.findByRole("heading", { name: "Texto" });
  expect(screen.getByText(/Autora/)).toBeTruthy();
  const original = screen
    .getByRole("link", { name: "Abrir fuente y documentos" })
    .getAttribute("href");
  fireEvent.click(screen.getByRole("button", { name: "Lista compacta" }));
  expect(
    screen
      .getByRole("link", { name: "Abrir fuente y documentos" })
      .getAttribute("href"),
  ).toBe(original);
  view.unmount();
  render(
    <InterfacePreferencesProvider>
      <LibraryPage context={context} search="" navigate={vi.fn()} />
    </InterfacePreferencesProvider>,
  );
  await screen.findByRole("heading", { name: "Texto" });
  expect(
    screen
      .getByRole("button", { name: "Lista compacta" })
      .getAttribute("aria-pressed"),
  ).toBe("true");
});
test("failed task save retains its exact draft and retries one creation identity", async () => {
  const fetch = vi
    .fn()
    .mockRejectedValueOnce(new Error("offline"))
    .mockResolvedValue(
      response({ id: "saved", revision: "a".repeat(64), fields: {} }),
    );
  vi.stubGlobal("fetch", fetch);
  const navigate = vi.fn();
  render(
    <ActivityWorkspace context={context} kind="backlog" navigate={navigate} />,
  );
  fireEvent.change(screen.getByLabelText("Proyecto"), {
    target: { value: "Migración" },
  });
  fireEvent.change(screen.getByLabelText("Tarea"), {
    target: { value: "Comparar grabaciones" },
  });
  fireEvent.change(screen.getByLabelText("Responsable"), {
    target: { value: "Persona" },
  });
  fireEvent.click(screen.getByRole("button", { name: "Guardar Backlog" }));
  await screen.findByRole("alert");
  expect(navigate).not.toHaveBeenCalled();
  expect((screen.getByLabelText("Tarea") as HTMLInputElement).value).toBe(
    "Comparar grabaciones",
  );
  const before = JSON.parse(fetch.mock.calls[0][1].body);
  fireEvent.click(screen.getByRole("button", { name: "Guardar Backlog" }));
  await waitFor(() =>
    expect(navigate).toHaveBeenCalledWith(
      "/study/notebook/backlog/saved?saved=" + "a".repeat(64),
    ),
  );
  expect(JSON.parse(fetch.mock.calls[1][1].body)).toEqual(before);
  expect(
    localStorage.getItem("mathmongo-activity-v1:owned:backlog:new"),
  ).toBeNull();
});
test("curated task payloads preserve typed lists, dates and explicit manual metrics", () => {
  expect(
    activityPayload("weekly", {
      ...activityValues("weekly"),
      iso_year: "2026",
      iso_week: "48",
      weekly_objectives: "A\nB",
      manual_override_metrics: "true",
      manual_real_hours: "3.5",
      manual_tasks_done: "2",
    }),
  ).toMatchObject({
    iso_year: 2026,
    iso_week: 48,
    weekly_objectives: ["A", "B"],
    manual_override_metrics: true,
    manual_real_hours: 3.5,
    manual_tasks_done: 2,
  });
  expect(activityPayload("backlog", activityValues("backlog"))).toMatchObject({
    estimate_hours: null,
    target_date: null,
    tags: [],
  });
});
test("display accents decode known LaTeX without changing unknown source", () => {
  expect(bibliographicText(String.raw`Introducci\'on`)).toContain(
    "Introducción",
  );
  expect(bibliographicText(String.raw`\unknown{keep}`)).toContain(
    String.raw`\unknown{keep}`,
  );
});
