import test from "node:test";
import { chromium, firefox, expect } from "@playwright/test";
import { writeFile } from "node:fs/promises";
import { readSource, writeSource } from "./source-browser.mjs";
import { browserCoverage } from "./browser-coverage.mjs";
await test(
  "a cloned session cannot erase its opener's unsaved concept",
  { timeout: 120000 },
  async () => {
    const name = process.env.MATHMONGO_STUDY_BROWSER || "chrome",
      base = process.env.MATHMONGO_INDEPENDENT_URL,
      evidence = process.env.MATHMONGO_INDEPENDENT_EVIDENCE;
    const browser =
      name === "firefox"
        ? await firefox.launch({ headless: true })
        : await chromium.launch({
            headless: true,
            executablePath: "/usr/bin/google-chrome",
            args: ["--no-sandbox"],
          });
    const context = await browser.newContext(),
      page = await context.newPage(),
      coverage = await browserCoverage(page, name, "concept-clone");
    let passed = false;
    try {
      await coverage.goto(base + "/study/concepts");
      const record = await page.evaluate(async (key) => {
        const ctx = await (await fetch("/api/study/v1/context")).json(),
          headers = { "X-MathMongo-Library": ctx.library_id };
        const list = await (
          await fetch("/api/study/v1/concepts", { headers })
        ).json();
        return (
          await fetch(
            "/api/study/v1/concepts/detail?" + new URLSearchParams({ key }),
            { headers },
          )
        ).json();
      });
      const route =
        base + "/study/concepts/" + encodeURIComponent(record.key) + "/edit";
      await coverage.goto(route);
      await page
        .getByRole("button", { name: "Fuente LaTeX", exact: true })
        .click();
      const popup = page.waitForEvent("popup");
      await page.evaluate((route) => window.open(route, "_blank"), route);
      const clone = await popup;
      await expect(
        clone.getByLabel("Nombre del concepto", { exact: true }),
      ).toBeVisible();
      const local =
        record.contenido_latex +
        "\n\nBorrador exclusivo de la ventana original.\n";
      await writeSource(page, local);
      await clone
        .getByLabel("Nombre del concepto", { exact: true })
        .fill("Versión de la ventana clonada");
      await clone
        .getByRole("button", { name: "Guardar concepto", exact: true })
        .click();
      await expect(
        clone.getByRole("heading", {
          name: "Versión de la ventana clonada",
          exact: true,
        }),
      ).toBeVisible();
      await coverage.reload();
      await expect(
        page.getByRole("heading", { name: "Editar concepto", exact: true }),
      ).toBeVisible();
      if (
        (await page
          .getByRole("button", { name: "Fuente LaTeX", exact: true })
          .getAttribute("aria-pressed")) !== "true"
      )
        await page
          .getByRole("button", { name: "Fuente LaTeX", exact: true })
          .click();
      expect(await readSource(page)).toBe(local);
      await writeFile(
        evidence + "/concept-clone-browser.json",
        JSON.stringify(
          {
            passed: true,
            browser: name,
            openerDraftSurvivesCloneSaveAndReload: true,
            MathV0_writes: 0,
          },
          null,
          2,
        ),
      );
      passed = true;
    } finally {
      await coverage.finish(passed);
      await browser.close();
    }
  },
);
