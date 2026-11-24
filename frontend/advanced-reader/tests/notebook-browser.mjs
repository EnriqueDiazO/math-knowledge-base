import test from "node:test";
import { chromium, firefox, expect } from "@playwright/test";
import { readFile, writeFile } from "node:fs/promises";
import { spawnSync } from "node:child_process";
import { browserCoverage } from "./browser-coverage.mjs";

await test(
  "Diario: visual writing, exact retry, associations, concurrency and portable LaTeX",
  { timeout: 180000 },
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
    const page = await browser.newPage({
      viewport: { width: 1440, height: 1080 },
      reducedMotion: "reduce",
    });
    page.setDefaultTimeout(25000);
    const coverage = await browserCoverage(page, name, "notebook"),
      errors = [];
    let passed = false;
    page.on("pageerror", (error) => errors.push(error.message));
    const button = (name) => page.getByRole("button", { name, exact: true });
    const request = (path, body) =>
      page.evaluate(
        async ({ path, body }) => {
          const context = await (await fetch("/api/study/v1/context")).json();
          const result = await fetch("/api/study/v1" + path, {
            method: body === undefined ? "GET" : "POST",
            headers: {
              "X-MathMongo-Library": context.library_id,
              ...(body === undefined
                ? {}
                : { "Content-Type": "application/json" }),
            },
            ...(body === undefined ? {} : { body: JSON.stringify(body) }),
          });
          if (!result.ok)
            throw new Error("Notebook readback failed: " + result.status);
          return result.json();
        },
        { path, body },
      );
    const shot = (name) =>
      page.screenshot({
        path: evidence + "/notebook-" + name + ".png",
        fullPage: true,
      });
    const download = async (label, file) => {
      const pending = page.waitForEvent("download");
      await button(label).click();
      const result = await pending;
      const path = evidence + "/" + file;
      await result.saveAs(path);
      return path;
    };
    try {
      await coverage.goto(base + "/study/notebook");
      await page
        .getByRole("link", { name: "+ Nueva entrada", exact: true })
        .click();
      await page
        .getByLabel("Título de la entrada", { exact: true })
        .fill("Diario visual recuperable");
      await page
        .getByText("Fecha, proyecto y etiquetas", { exact: true })
        .click();
      await page
        .getByLabel("Proyecto", { exact: true })
        .fill("Cuaderno temporal");
      await page
        .getByLabel("Etiquetas (una por línea)", { exact: true })
        .fill("coma, literal\nsegunda");
      await page
        .getByText("Referencias de la entrada", { exact: true })
        .click();
      await page
        .getByRole("combobox", { name: "Fuente administrada", exact: true })
        .selectOption(process.env.MATHMONGO_PALETTE_SOURCE);
      const choices = await request(
        "/sources/" + process.env.MATHMONGO_PALETTE_SOURCE + "/references",
      );
      const referenceId = choices.items[0].reference_id;
      await page
        .getByRole("combobox", {
          name: "Referencia bibliográfica",
          exact: true,
        })
        .selectOption(referenceId);
      await button("Vincular referencia a la entrada").click();
      await page
        .locator(".visual-document .tiptap")
        .fill("Escritura de Diario con fórmula.");
      await button("Insertar fórmula en línea").click();
      await page
        .locator("math-field")
        .last()
        .evaluate((field) => {
          field.value = String.raw`\frac{1}{2}`;
          field.dispatchEvent(new InputEvent("input", { bubbles: true }));
        });
      await button("Volver al párrafo").click();
      const advanced = String.raw`\newcommand{\diaryMacro}[1]{#1^2}
Texto protegido $\diaryMacro{x}$.
\begin{tikzpicture}\draw[blue] (0,0)--(1,0)--(1,1);\end{tikzpicture}`;
      await button("Bloque LaTeX avanzado").click();
      await page
        .getByLabel("Código LaTeX protegido", { exact: true })
        .fill(advanced);
      await button("Conservar bloque").click();
      await shot("visual-math-and-protected-tikz");
      let lost = false;
      const writes = [];
      await page.route("**/api/study/v1/notebook", async (route) => {
        if (route.request().method() !== "POST") return route.continue();
        writes.push(route.request().postDataJSON());
        if (!lost) {
          lost = true;
          const response = await route.fetch();
          expect(response.ok()).toBe(true);
          await route.abort("failed");
        } else await route.continue();
      });
      await button("Guardar entrada").click();
      await expect(button("Reintentar el mismo guardado")).toBeVisible();
      await coverage.reload();
      await button("Reintentar el mismo guardado").click();
      await expect(page).toHaveURL(/\/study\/notebook\/diary_/u);
      expect(writes).toHaveLength(2);
      expect(writes[1]).toEqual(writes[0]);
      const noteId = new URL(page.url()).pathname.split("/").at(-1),
        path = "/notebook/" + noteId;
      const first = await request(path);
      expect(first.latex_body).toContain(advanced);
      expect(first.latex_body).toContain(String.raw`\frac{1}{2}`);
      expect(first.tags).toEqual(["coma, literal", "segunda"]);
      expect(first.references[0].catalog_reference_id).toBe(referenceId);
      await coverage.reload();
      await expect(
        page.getByLabel("Título de la entrada", { exact: true }),
      ).toHaveValue("Diario visual recuperable");
      const pdf = await download("Exportar PDF", "notebook-visual.pdf");
      expect((await readFile(pdf)).subarray(0, 5).toString()).toBe("%PDF-");
      const text = spawnSync("pdftotext", [pdf, "-"], { encoding: "utf8" });
      expect(text.status).toBe(0);
      expect(text.stdout).toContain("Texto protegido");
      await download("Exportar proyecto TEX", "notebook-visual-tex.zip");
      await page
        .locator(".visual-document .tiptap p")
        .first()
        .fill("Edición localizada del Diario.");
      await button("Guardar entrada").click();
      await expect(
        page.getByText("Entrada guardada y confirmada en esta biblioteca.", {
          exact: true,
        }),
      ).toBeVisible();
      const mixed = await request(path);
      expect(mixed.latex_body).toContain(advanced);
      await shot("saved-and-recovered");
      await page
        .getByLabel("Título de la entrada", { exact: true })
        .fill("Mi título tras conflicto");
      const remote = await request(path);
      await request(path, {
        revision: remote.revision,
        changes: { project: "Proyecto de otra ventana" },
      });
      await button("Guardar entrada").click();
      await expect(
        page.getByText(/Otra ventana cambió la entrada/),
      ).toBeVisible();
      await button("Consultar versión guardada").click();
      await button("Continuar sobre esta versión").click();
      await page
        .getByText("Fecha, proyecto y etiquetas", { exact: true })
        .click();
      await expect(page.getByLabel("Proyecto", { exact: true })).toHaveValue(
        "Proyecto de otra ventana",
      );
      await expect(
        page.getByLabel("Título de la entrada", { exact: true }),
      ).toHaveValue("Mi título tras conflicto");
      await button("Guardar entrada").click();
      await expect(
        page.getByText("Entrada guardada y confirmada en esta biblioteca.", {
          exact: true,
        }),
      ).toBeVisible();
      expect((await request(path)).latex_body).toContain(advanced);
      await coverage.goto(base + "/study/notebook/historical-diary");
      await expect(
        page.getByLabel("Título de la entrada", { exact: true }),
      ).toHaveValue("Diario histórico de prueba");
      await button("Guardar entrada").click();
      await expect(
        page.getByText("Entrada guardada y confirmada en esta biblioteca.", {
          exact: true,
        }),
      ).toBeVisible();
      await coverage.goto(
        base + "/study/sources/" + process.env.MATHMONGO_PALETTE_SOURCE,
      );
      await page
        .getByRole("link", {
          name: "Entradas del Cuaderno con referencias de esta fuente",
          exact: true,
        })
        .click();
      await expect(
        page.getByRole("link", {
          name: "Mi título tras conflicto",
          exact: true,
        }),
      ).toBeVisible();
      await shot("source-linked-entries");
      await page.setViewportSize({ width: 700, height: 960 });
      await shot("narrow");
      expect(
        await page.evaluate(
          () => document.documentElement.scrollWidth <= innerWidth + 1,
        ),
      ).toBe(true);
      expect(errors).toEqual([]);
      passed = true;
      await writeFile(
        evidence + "/notebook-browser.json",
        JSON.stringify(
          {
            passed,
            browser: name,
            version: browser.version(),
            noteId,
            referenceId,
            sourceId: process.env.MATHMONGO_PALETTE_SOURCE,
            protectedLatex: advanced,
            errors,
          },
          null,
          2,
        ),
      );
    } finally {
      if (!passed) await shot("failed");
      await coverage.finish(passed);
      await browser.close();
    }
  },
);
