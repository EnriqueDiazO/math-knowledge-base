import test from "node:test";
import { chromium, firefox, expect } from "@playwright/test";
import { writeFile } from "node:fs/promises";
import { readSource, writeSource } from "./source-browser.mjs";
import { browserCoverage } from "./browser-coverage.mjs";
await test(
  "closed browser drafts are discoverable without saving or overwriting their originals",
  { timeout: 120000 },
  async () => {
    const name = process.env.MATHMONGO_STUDY_BROWSER || "chrome",
      base = process.env.MATHMONGO_INDEPENDENT_URL,
      evidence = process.env.MATHMONGO_INDEPENDENT_EVIDENCE,
      key = process.env.MATHMONGO_CLONE_CONCEPT_KEY,
      route = base + "/study/concepts/" + encodeURIComponent(key) + "/edit";
    const launch = () =>
      name === "firefox"
        ? firefox.launchPersistentContext(process.env.MATHMONGO_TEST_PROFILE, {
            headless: true,
          })
        : chromium.launchPersistentContext(process.env.MATHMONGO_TEST_PROFILE, {
            headless: true,
            executablePath: "/usr/bin/google-chrome",
            args: ["--no-sandbox"],
          });
    const read = (page) =>
      page.evaluate(async (key) => {
        const context = await (await fetch("/api/study/v1/context")).json();
        return (
          await fetch(
            "/api/study/v1/concepts/detail?" + new URLSearchParams({ key }),
            { headers: { "X-MathMongo-Library": context.library_id } },
          )
        ).json();
      }, key);
    let context = await launch();
    let page = context.pages()[0] || (await context.newPage());
    let coverage,
      passed = false;
    try {
      await page.goto(route);
      const before = await read(page);
      await page
        .getByRole("button", { name: "Fuente LaTeX", exact: true })
        .click();
      const local =
        before.contenido_latex + "\n\\macroSoloLocal{Sin publicar, á}\n";
      await writeSource(page, local);
      const archives = await page.evaluate(() =>
        Object.fromEntries(
          Object.entries(localStorage).filter(([key]) =>
            key.includes("-study-concepts-window-"),
          ),
        ),
      );
      // Actually close the browser; do not simulate recovery by mutating product storage.
      await context.close();
      context = await launch();
      page = context.pages()[0] || (await context.newPage());
      coverage = await browserCoverage(page, name, "concept-cold-recovery");
      await coverage.goto(route);
      expect(await read(page)).toEqual(before);
      await page
        .getByText("Recuperar borradores de otras ventanas", { exact: true })
        .click();
      await page
        .getByRole("button", { name: "Buscar borradores locales", exact: true })
        .click();
      await page
        .getByRole("button", { name: "Recuperar una copia", exact: true })
        .click();
      await expect(page.getByRole("status")).toContainText(
        "Todavía no se ha guardado",
      );
      if (
        (await page
          .getByRole("button", { name: "Fuente LaTeX", exact: true })
          .getAttribute("aria-pressed")) !== "true"
      )
        await page
          .getByRole("button", { name: "Fuente LaTeX", exact: true })
          .click();
      expect(await readSource(page)).toBe(local);
      expect(await read(page)).toEqual(before);
      for (const [key, raw] of Object.entries(archives))
        expect(
          await page.evaluate((key) => localStorage.getItem(key), key),
        ).toBe(raw);
      await coverage.reload();
      expect(await readSource(page)).toBe(local);
      await page.screenshot({
        path: evidence + "/concept-cold-recovery.png",
        fullPage: true,
      });
      await page
        .getByRole("button", { name: "Guardar concepto", exact: true })
        .click();
      await expect(
        page.getByRole("heading", { name: before.titulo, exact: true }),
      ).toBeVisible();
      expect((await read(page)).contenido_latex).toBe(local);
      await writeFile(
        evidence + "/concept-cold-recovery.json",
        JSON.stringify(
          {
            passed: true,
            browser: name,
            realBrowserClosed: true,
            copiedWithoutSaving: true,
            originalArchivesUnchanged: true,
            exactReload: true,
            explicitSave: true,
            MathV0_writes: 0,
          },
          null,
          2,
        ),
      );
      passed = true;
    } finally {
      if (coverage) await coverage.finish(passed);
      await context.close();
    }
  },
);
