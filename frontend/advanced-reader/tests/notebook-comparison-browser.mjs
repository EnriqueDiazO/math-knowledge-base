/** Visible-menu to real persistence and CSV, with short recorded clips and isolated comparison data. */
import { browserCoverage } from "./browser-coverage.mjs";
import { chromium, firefox, expect } from "@playwright/test";
import { mkdir, readFile, writeFile } from "node:fs/promises";
import { resolve } from "node:path";
const root = resolve("../../evidence/sonar/cpi-five-images-2026-11-24"),
  own = JSON.parse(
    await readFile(resolve(root, "owned-comparison.json"), "utf8"),
  ),
  name = process.env.MATHMONGO_STUDY_BROWSER || "firefox",
  out = resolve(root, "notebook-after-" + name);
await mkdir(out, { recursive: true, mode: 0o700 });
const browser =
    name === "chrome"
      ? await chromium.launch({
          headless: true,
          executablePath: "/usr/bin/google-chrome",
          args: ["--no-sandbox"],
        })
      : await firefox.launch({ headless: true }),
  context = await browser.newContext({
    viewport: { width: 1440, height: 1000 },
    recordVideo: { dir: out, size: { width: 1440, height: 1000 } },
    reducedMotion: "reduce",
  }),
  proof = { browser: name, clips: [], errors: [] },
  prefix = "Comparación " + name + " " + Date.now();
async function clip(label, operation) {
  process.env.MATHMONGO_INDEPENDENT_EVIDENCE = out;
  process.env.MATHMONGO_INDEPENDENT_URL = own.instances.react.url;
  const page = await context.newPage(),
    start = Date.now(),
    events = [];
  page.setDefaultTimeout(25000);
  page.on("pageerror", (error) => proof.errors.push(error.message));
  const mark = async (description) => {
    events.push({ seconds: (Date.now() - start) / 1000, description });
    await page.screenshot({
      path: resolve(out, label + "-" + events.length + ".png"),
      fullPage: true,
    });
    await page.waitForTimeout(600);
  };
  const coverage = await browserCoverage(page, name, "notebook-" + label);
  let passed = false;
  try {
    await coverage.goto(own.instances.react.url + "/study");
    await expect(
      page.getByRole("navigation", {
        name: "Navegación principal",
        exact: true,
      }),
    ).toBeVisible();
    await operation(page, mark, coverage);
    passed = true;
  } finally {
    await coverage.finish(passed);
    await page.close();
    await page.video().saveAs(resolve(out, label + ".webm"));
    proof.clips.push({ label, events, seconds: (Date.now() - start) / 1000 });
  }
}
async function menu(page, label) {
  await page
    .getByRole("navigation", { name: "Navegación principal", exact: true })
    .getByRole("link", { name: label, exact: true })
    .click();
}
try {
  await clip("menu", async (page, mark) => {
    proof.navigation = await page
      .getByRole("navigation", { name: "Navegación principal", exact: true })
      .getByRole("link")
      .evaluateAll((nodes) =>
        nodes.map((node) => ({
          label: node.textContent,
          path: node.getAttribute("href"),
        })),
      );
    await mark("All groups expanded");
    for (const label of ["Diario", "Cornell", "CPI", "Diagnóstico"]) {
      await menu(page, label);
      await expect(page.locator("h1")).toBeVisible();
      await mark(label + " from main navigation");
    }
  });
  for (const [kind, label] of [
    ["worklog", "Worklog"],
    ["backlog", "Backlog"],
    ["deliverables", "Deliverables"],
    ["weekly", "Weekly Review"],
  ])
    await clip(kind, async (page, mark, coverage) => {
      await menu(page, label);
      await expect(
        page.getByRole("heading", { name: label, exact: true }),
      ).toBeVisible();
      await mark("Historical list and visible create action");
      await page
        .getByRole("link", { name: "Crear " + label, exact: true })
        .click();
      if (kind === "weekly") {
        await page.getByLabel("Año ISO", { exact: true }).fill("2026");
        const currentContext = await (
          await page.request.get(
            own.instances.react.url + "/api/study/v1/context",
          )
        ).json();
        const weeks = await (
          await page.request.get(
            own.instances.react.url + "/api/study/v1/activities/weekly",
            { headers: { "X-MathMongo-Library": currentContext.library_id } },
          )
        ).json();
        const used = new Set(
          weeks.items
            .filter((item) => item.fields.iso_year === 2026)
            .map((item) => item.fields.iso_week),
        );
        const free = Array.from(
          { length: 26 },
          (_, index) => index + 1 + (name === "chrome" ? 0 : 26),
        ).find((week) => !used.has(week));
        if (!free)
          throw new Error("No free comparison week; preserve existing records");
        await page.getByLabel("Semana ISO", { exact: true }).fill(String(free));
        await page
          .getByLabel("Objetivos (uno por línea)", { exact: true })
          .fill(prefix + "\nComprobar recuperación");
        await page
          .getByLabel("Logros (uno por línea)", { exact: true })
          .fill("Contrato conservado");
      } else {
        await page.getByLabel("Proyecto", { exact: true }).fill(prefix);
        if (kind === "deliverables") {
          await page
            .getByLabel("Nombre del entregable", { exact: true })
            .fill(prefix + " informe");
          await page
            .getByLabel("Ruta o URL", { exact: true })
            .fill("https://example.org/evidencia");
        } else {
          await page
            .getByLabel("Tarea", { exact: true })
            .fill(prefix + " tarea");
          if (kind === "backlog")
            await page
              .getByLabel("Responsable", { exact: true })
              .fill("Persona");
          else await page.getByLabel("Horas", { exact: true }).fill("2.5");
        }
      }
      if (kind === "backlog") {
        await page
          .getByLabel("Fecha objetivo", { exact: true })
          .fill("2026-12-01");
        await page.getByLabel("Horas estimadas", { exact: true }).fill("1.5");
        await page
          .getByLabel("Prioridad", { exact: true })
          .selectOption("Alta");
        await page
          .getByLabel("Etiquetas separadas por comas", { exact: true })
          .fill("migración, evidencia");
        await page.route("**/api/study/v1/activities/backlog", (route) =>
          route.abort("failed"),
        );
        await page
          .getByRole("button", { name: "Guardar " + label, exact: true })
          .click();
        await expect(page.getByRole("alert")).toContainText("borrador");
        await expect(page.getByLabel("Tarea", { exact: true })).toHaveValue(
          prefix + " tarea",
        );
        await mark("Failed save retains draft, without announcing success");
        await page.unroute("**/api/study/v1/activities/backlog");
      }
      await page
        .getByRole("button", { name: "Guardar " + label, exact: true })
        .click();
      await expect(
        page.getByRole("heading", { name: "Editar " + label, exact: true }),
      ).toBeVisible();
      const saved = page.url();
      const savedId = new URL(saved).pathname.split("/").at(-1);
      await coverage.reload();
      await expect(
        page.getByRole("heading", { name: "Editar " + label, exact: true }),
      ).toBeVisible();
      await expect(
        page.getByLabel(
          kind === "weekly" ? "Objetivos (uno por línea)" : "Proyecto",
          { exact: true },
        ),
      ).toHaveValue(
        kind === "weekly" ? prefix + "\nComprobar recuperación" : prefix,
      );
      if (kind === "backlog") {
        await expect(
          page.getByLabel("Fecha objetivo", { exact: true }),
        ).toHaveValue("2026-12-01");
        await expect(
          page.getByLabel("Etiquetas separadas por comas", { exact: true }),
        ).toHaveValue("migración, evidencia");
        await expect(page.getByLabel("Prioridad", { exact: true })).toHaveValue(
          "Alta",
        );
      }
      await mark("Saved, reloaded and reopened from real MongoDB");
      if (kind !== "weekly")
        await page
          .getByLabel("Proyecto", { exact: true })
          .fill(prefix + " editado");
      else
        await page
          .getByLabel("Logros (uno por línea)", { exact: true })
          .fill("Guardado y editado");
      await page
        .getByRole("button", { name: "Guardar " + label, exact: true })
        .click();
      await expect(page).not.toHaveURL(saved);
      await coverage.reload();
      await expect(
        page.getByLabel(
          kind === "weekly" ? "Logros (uno por línea)" : "Proyecto",
          { exact: true },
        ),
      ).toHaveValue(
        kind === "weekly" ? "Guardado y editado" : prefix + " editado",
      );
      await mark("Edited metadata persists after second reload");
      await menu(page, label);
      if (kind !== "weekly") {
        await page
          .getByLabel("Buscar tareas o entregables", { exact: true })
          .fill(prefix);
        await page
          .getByRole("button", { name: "Buscar registros", exact: true })
          .click();
      }
      const selection = page
        .locator("article")
        .filter({
          has: page.locator(
            'a[href="/study/notebook/' + kind + "/" + savedId + '"]',
          ),
        })
        .getByRole("checkbox");
      await expect(selection).toBeVisible();
      await selection.check();
      const download = page.waitForEvent("download");
      await page
        .getByRole("button", { name: "Exportar selección CSV", exact: true })
        .click();
      const file = await download;
      await file.saveAs(resolve(out, kind + ".csv"));
      const csv = await readFile(resolve(out, kind + ".csv"), "utf8");
      expect(csv).toContain(
        kind === "weekly" ? "Guardado y editado" : prefix + " editado",
      );
      await mark("Selected CSV downloaded with persisted fields");
    });
  await clip("kanban", async (page, mark, coverage) => {
    await menu(page, "Kanban");
    await page
      .getByLabel("Buscar tareas o entregables", { exact: true })
      .fill(prefix);
    await page
      .getByRole("button", { name: "Buscar registros", exact: true })
      .click();
    const card = page
      .locator(".kanban-columns article")
      .filter({ hasText: prefix + " tarea" });
    await expect(card).toHaveCount(1);
    await card.getByRole("combobox").selectOption("Done");
    await card
      .getByRole("button", { name: "Aplicar estado", exact: true })
      .click();
    await expect(
      page
        .locator(".kanban-columns section")
        .filter({
          has: page.getByRole("heading", { name: "Done", exact: true }),
        })
        .getByRole("heading", { name: prefix + " tarea" }),
    ).toBeVisible();
    await coverage.reload();
    await expect(
      page
        .locator(".kanban-columns section")
        .filter({
          has: page.getByRole("heading", { name: "Done", exact: true }),
        })
        .getByRole("heading", { name: prefix + " tarea" }),
    ).toBeVisible();
    await mark("Kanban Done transition persists in the same Backlog record");
  });
  proof.passed = true;
} catch (error) {
  proof.passed = false;
  proof.error = String(error);
  throw error;
} finally {
  await writeFile(resolve(out, "browser.json"), JSON.stringify(proof, null, 2));
  await context.close();
  await browser.close();
}
