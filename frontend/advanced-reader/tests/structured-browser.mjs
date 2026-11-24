import test from "node:test";
import { chromium, firefox, expect } from "@playwright/test";
import { writeFile, readFile } from "node:fs/promises";
import { spawnSync } from "node:child_process";
import { browserCoverage } from "./browser-coverage.mjs";

await test(
  "Cornell then CPI: real region editing, exact retry, persistence, pages and isolated export",
  { timeout: 240000 },
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
    const coverage = await browserCoverage(page, name, "structured"),
      errors = [],
      proof = [];
    let passed = false;
    page.on("pageerror", (error) => errors.push(error.message));
    const button = (name) => page.getByRole("button", { name, exact: true });
    const request = (path, body) =>
      page.evaluate(
        async ({ path, body }) => {
          const ctx = await (await fetch("/api/study/v1/context")).json();
          const result = await fetch("/api/study/v1" + path, {
            method: body === undefined ? "GET" : "POST",
            headers: {
              "X-MathMongo-Library": ctx.library_id,
              ...(body === undefined
                ? {}
                : { "Content-Type": "application/json" }),
            },
            ...(body === undefined ? {} : { body: JSON.stringify(body) }),
          });
          if (!result.ok)
            throw new Error(
              "Structured readback failed: " +
                result.status +
                " " +
                (await result.text()),
            );
          return result.json();
        },
        { path, body },
      );
    const shot = (label) =>
      page.screenshot({
        path: evidence + "/structured-" + label + ".png",
        fullPage: true,
      });
    const download = async (label, file) => {
      const pending = page.waitForEvent("download");
      await button(label).click();
      const path = evidence + "/" + file;
      await (await pending).saveAs(path);
      return path;
    };
    try {
      for (const family of ["cornell", "cpi"]) {
        const title = family === "cornell" ? "Cornell" : "CPI",
          labels =
            family === "cornell"
              ? ["Ideas y preguntas", "Desarrollo", "Síntesis"]
              : ["Comprensión", "Producción", "Integración"],
          keys =
            family === "cornell"
              ? ["cue", "main", "summary"]
              : ["comprehension", "production", "integration"];
        await coverage.goto(base + "/study/notebook");
        await page.getByRole("link", { name: title, exact: true }).click();
        await page
          .getByRole("link", { name: "+ Nueva nota " + title, exact: true })
          .click();
        await page
          .getByLabel("Título de la nota", { exact: true })
          .fill(title + " desde React");
        await page
          .locator(".visual-document .tiptap")
          .fill("Pregunta conservada sobre límites.");
        await button(labels[1]).click();
        await page
          .locator(".visual-document .tiptap")
          .fill("Desarrollo con fórmula y figura.");
        await button("Insertar fórmula en línea").click();
        await page
          .locator("math-field")
          .last()
          .evaluate((field) => {
            field.value = String.raw`\frac{x_i}{1+x^2}`;
            field.dispatchEvent(new InputEvent("input", { bubbles: true }));
          });
        await button("Volver al párrafo").click();
        const sourceId = process.env.MATHMONGO_PALETTE_SOURCE,
          references = await request("/sources/" + sourceId + "/references"),
          referenceId = references.items[0].reference_id;
        const chooseCitation = async () => {
          await page
            .getByText("Insertar referencia bibliográfica", { exact: true })
            .click();
          await page
            .getByRole("combobox", { name: "Fuente administrada", exact: true })
            .selectOption(sourceId);
          await page
            .getByRole("combobox", {
              name: "Referencia bibliográfica",
              exact: true,
            })
            .selectOption(referenceId);
        };
        if (family === "cornell") {
          await chooseCitation();
          let release;
          const refUrl =
            "**/api/study/v1/structured/" +
            family +
            "/references/" +
            referenceId;
          await page.route(refUrl, async (route) => {
            await new Promise((resolve) => {
              release = resolve;
            });
            await route.continue();
          });
          await button("Insertar cita en esta región").click();
          await expect.poll(() => !!release).toBe(true);
          await button(labels[0]).click();
          const response = page.waitForResponse((res) =>
            res.url().endsWith("/references/" + referenceId),
          );
          release();
          await (await response).finished();
          await page.evaluate(() => new Promise(requestAnimationFrame));
          await page.unroute(refUrl);
          await expect(page.locator(".visual-document .tiptap")).toContainText(
            "Pregunta conservada",
          );
          await button(labels[1]).click();
          await expect(page.locator(".visual-document .tiptap")).toContainText(
            "Desarrollo con fórmula",
          );
        }
        await chooseCitation();
        await button("Insertar cita en esta región").click();
        await expect(
          page.getByText(
            "Cita incorporada al borrador; guarda para conservarla en la biblioteca.",
            { exact: true },
          ),
        ).toBeVisible();
        await expect(page.locator(".visual-document .tiptap")).toContainText(
          "Lectura de álgebra",
        );
        const protectedLatex = String.raw`\newcommand{\localStudy}[1]{#1^2}
Texto protegido $\localStudy{x}$.
\begin{tikzpicture}\draw[blue] (0,0)--(0.5,0)--(0.5,0.3);\end{tikzpicture}`;
        await button("Bloque LaTeX avanzado").click();
        await page
          .getByLabel("Código LaTeX protegido", { exact: true })
          .fill(protectedLatex);
        await button("Conservar bloque").click();
        await button(labels[2]).click();
        await page
          .locator(".visual-document .tiptap")
          .fill("Síntesis preservada tras recargar.");
        await button(labels[0]).click();
        await expect(page.locator(".visual-document .tiptap")).toContainText(
          "Pregunta conservada",
        );
        let lost = false;
        const writes = [];
        await page.route(
          "**/api/study/v1/structured/" + family,
          async (route) => {
            if (route.request().method() !== "POST") return route.continue();
            writes.push(route.request().postDataJSON());
            if (!lost) {
              lost = true;
              const response = await route.fetch();
              expect(response.ok()).toBe(true);
              await route.abort("failed");
            } else await route.continue();
          },
        );
        await button("Guardar nota " + title).click();
        await expect(button("Reintentar el mismo guardado")).toBeVisible();
        await coverage.reload();
        await button("Reintentar el mismo guardado").click();
        await expect(page).toHaveURL(
          new RegExp("/study/notebook/" + family + "/" + family + "_", "u"),
        );
        expect(writes).toHaveLength(2);
        expect(writes[1]).toEqual(writes[0]);
        await page.unroute("**/api/study/v1/structured/" + family);
        const identity = new URL(page.url()).pathname.split("/").at(-1),
          path = "/structured/" + family + "/" + identity;
        let saved = await request(path);
        expect(saved.document.pages).toHaveLength(1);
        expect(saved.document.pages[0][keys[0]].latex).toContain(
          "Pregunta conservada",
        );
        expect(saved.document.pages[0][keys[1]].latex).toContain(
          protectedLatex,
        );
        expect(saved.document.pages[0][keys[1]].latex).toContain(
          "Lectura de álgebra",
        );
        expect(saved.document.pages[0][keys[1]].latex).toContain(
          String.raw`\frac{x_i}{1+x^2}`,
        );
        const first = saved.document.pages[0];
        await button(labels[1]).click();
        await shot(family + "-visual-math-tikz");
        await download("Exportar proyecto TEX", family + "-project.zip");
        const pdf = await download("Exportar PDF", family + "-classic.pdf");
        expect((await readFile(pdf)).subarray(0, 5).toString()).toBe("%PDF-");
        const text = spawnSync("pdftotext", ["-layout", pdf, "-"], {
          encoding: "utf8",
        });
        expect(text.status).toBe(0);
        expect(text.stdout.replace(/\s+/gu, " ")).toContain(
          "Pregunta conservada",
        );
        expect(text.stdout.replace(/\s+/gu, " ")).toContain(
          "Síntesis preservada",
        );
        await button("Comprobar ajuste de la nota guardada").click();
        await expect(
          page.getByText(
            "Las regiones caben en la plantilla. El contenido guardado permanece intacto.",
            { exact: true },
          ),
        ).toBeVisible();
        await button(labels[2]).click();
        await page
          .locator(".visual-document .tiptap")
          .fill("Síntesis editada desde React.");
        await button("Guardar nota " + title).click();
        await expect(
          page.getByText("Nota guardada y confirmada en esta biblioteca.", {
            exact: true,
          }),
        ).toBeVisible();
        saved = await request(path);
        expect(saved.document.pages[0][keys[0]]).toEqual(first[keys[0]]);
        expect(saved.document.pages[0][keys[1]]).toEqual(first[keys[1]]);
        await button("Duplicar página").click();
        await button("Mover página antes").click();
        await button("Guardar nota " + title).click();
        await expect(
          page.getByText("Nota guardada y confirmada en esta biblioteca.", {
            exact: true,
          }),
        ).toBeVisible();
        expect((await request(path)).document.pages).toHaveLength(2);
        await button("Retirar página").click();
        await button("Confirmar retirada de esta página").click();
        await button("Guardar nota " + title).click();
        await expect(
          page.getByText("Nota guardada y confirmada en esta biblioteca.", {
            exact: true,
          }),
        ).toBeVisible();
        await page
          .getByText("Fecha, proyecto y etiquetas", { exact: true })
          .click();
        await page
          .getByLabel("Plantilla de la nota", { exact: true })
          .selectOption(family + "_hybrid_compact_v1");
        await button("Guardar nota " + title).click();
        await expect(
          page.getByText("Nota guardada y confirmada en esta biblioteca.", {
            exact: true,
          }),
        ).toBeVisible();
        await download("Exportar PDF", family + "-hybrid.pdf");
        await coverage.reload();
        await expect(
          page.getByLabel("Título de la nota", { exact: true }),
        ).toHaveValue(title + " desde React");
        await button(labels[1]).click();
        await expect(page.locator(".visual-document")).toContainText(
          "Desarrollo con fórmula",
        );
        await shot(family + "-saved-recovered");
        await page.setViewportSize({ width: 480, height: 900 });
        await shot(family + "-narrow");
        expect(
          await page.evaluate(
            () => document.documentElement.scrollWidth <= innerWidth + 1,
          ),
        ).toBe(true);
        await page.setViewportSize({ width: 1440, height: 1080 });
        saved = await request(path);
        await request(path, {
          revision: saved.revision,
          metadata: { title: "Versión de otra ventana" },
          document: saved.document,
        });
        await page
          .getByLabel("Título de la nota", { exact: true })
          .fill("Mi borrador en conflicto");
        await button("Guardar nota " + title).click();
        await expect(button("Consultar versión guardada")).toBeVisible();
        await expect(
          page.getByLabel("Título de la nota", { exact: true }),
        ).toHaveValue("Mi borrador en conflicto");
        await button("Consultar versión guardada").click();
        await button("Archivar borrador y abrir versión guardada").click();
        await expect(
          page.getByLabel("Título de la nota", { exact: true }),
        ).toHaveValue("Versión de otra ventana");
        expect(
          await page.evaluate(() =>
            Object.keys(localStorage).some((key) => key.includes("-archive-")),
          ),
        ).toBe(true);
        saved = await request(path);
        proof.push({
          family,
          noteId: identity,
          protectedLatex,
          title: saved.metadata.title,
          template: saved.document.template_id,
          regions: keys,
          exactRetry: true,
          conflictPreserved: true,
        });
      }
      expect(errors).toEqual([]);
      await writeFile(
        evidence + "/structured-browser.json",
        JSON.stringify({ browser: name, passed: true, cases: proof }, null, 2),
      );
      passed = true;
    } catch (error) {
      await shot("failure");
      console.error(await page.locator("main").innerText());
      throw error;
    } finally {
      await coverage.finish(passed);
      await browser.close();
    }
  },
);
