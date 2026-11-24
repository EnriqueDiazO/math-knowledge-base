import test from "node:test";
import { chromium, firefox, expect } from "@playwright/test";
import { writeFile, readFile } from "node:fs/promises";
import { spawnSync } from "node:child_process";
import { browserCoverage } from "./browser-coverage.mjs";

await test(
  "MathLive tools preserve the surrounding expression and protected document",
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
      }),
      coverage = await browserCoverage(page, name, "math-tools");
    let passed = false;
    try {
      await coverage.goto(base + "/study/notebook/new");
      await page
        .getByRole("button", {
          name: "Insertar fórmula en bloque",
          exact: true,
        })
        .click();
      const field = page.locator("math-field").last();
      await field.evaluate((element) => {
        element.value = "a+b";
        element.position = -1;
        element.focus();
        element.dispatchEvent(new InputEvent("input", { bubbles: true }));
      });
      await page.getByRole("button", { name: "Raíz", exact: true }).click();
      const latex = await field.evaluate((element) => element.value);
      await writeFile(
        evidence + "/math-tools-insertion.json",
        JSON.stringify(
          { browser: name, latex, preservesOriginal: latex.includes("a+b") },
          null,
          2,
        ),
      );
      expect(latex).toContain("a+b");
      expect(latex).toContain(String.raw`\sqrt`);
      await field.evaluate((element) => {
        element.insert("c");
        element.dispatchEvent(new InputEvent("input", { bubbles: true }));
      });
      const completed = await field.evaluate((element) => element.value);
      expect(completed).toContain("a+b");
      expect(completed).toContain(String.raw`\sqrt{c}`);
      await page
        .getByText("Más herramientas matemáticas", { exact: true })
        .click();
      const button = (label) =>
        page.getByRole("button", { name: label, exact: true });
      await field.evaluate((element) => {
        element.position = -1;
        element.insert("+d");
        element.dispatchEvent(new InputEvent("input", { bubbles: true }));
      });
      const withD = await field.evaluate((element) => element.value);
      expect(withD).toContain("+d");
      await button("Deshacer fórmula").click();
      expect(await field.evaluate((element) => element.value)).not.toBe(withD);
      await button("Rehacer fórmula").click();
      expect(await field.evaluate((element) => element.value)).toBe(withD);
      await field.evaluate((element) => {
        element.value = "a+b+c";
        element.selection = { ranges: [[2, 3]], direction: "forward" };
        element.focus();
        element.dispatchEvent(new InputEvent("input", { bubbles: true }));
      });
      expect(
        await field.evaluate((element) =>
          element.getValue(element.selection, "latex"),
        ),
      ).toBe("b");
      await button("Raíz").click();
      expect(await field.evaluate((element) => element.value)).toBe(
        String.raw`a+\sqrt{b}+c`,
      );
      await field.evaluate((element) => {
        element.value = String.raw`\frac{a_{i}+\sqrt{b}}{1+x^2}+\sum_{n=1}^3n`;
        element.position = -1;
        element.focus();
        element.dispatchEvent(new InputEvent("input", { bubbles: true }));
      });
      const nested = await field.evaluate((element) => element.value);
      await page
        .getByLabel("Buscar estructura matemática", { exact: true })
        .fill("norma");
      await field.evaluate((element) => {
        element.executeCommand("selectAll");
        element.focus();
      });
      await button("Norma").click();
      const wrapped = await field.evaluate((element) => element.value);
      expect(wrapped).toContain(nested);
      expect(wrapped).toContain(String.raw`\lVert`);
      // A separate formula demonstrates variable dimensions, without replacing the first.
      await button("Volver al párrafo").click();
      await button("Insertar fórmula en bloque").click();
      const matrix = page.locator("math-field").last();
      await page.getByLabel("Filas de la matriz", { exact: true }).fill("3");
      await page.getByLabel("Columnas de la matriz", { exact: true }).fill("2");
      await page
        .getByLabel("Delimitadores de la matriz", { exact: true })
        .selectOption("bmatrix");
      await button("Insertar matriz configurable").click();
      const matrixSource = await matrix.evaluate((element) => element.value);
      expect(matrixSource).toBe(
        String.raw`\begin{bmatrix}0&0\\0&0\\0&0\end{bmatrix}`,
      );
      const matrixEnd = await matrix.evaluate((element) => {
        element.position = -1;
        return element.position;
      });
      // MathLive's model focus flag precedes its deferred DOM focus. Confirm the actual target.
      await expect
        .poll(() =>
          matrix.evaluate((element) => {
            element.focus();
            return document.activeElement === element;
          }),
        )
        .toBe(true);
      await page.keyboard.press("ArrowLeft");
      await expect
        .poll(() => matrix.evaluate((element) => element.position))
        .toBeLessThan(matrixEnd);
      expect(await matrix.evaluate((element) => element.value)).toBe(
        matrixSource,
      );
      expect(
        await page
          .locator("math-field")
          .first()
          .evaluate((element) => element.value),
      ).toBe(wrapped);
      await page.getByLabel("Filas de la matriz", { exact: true }).fill("9");
      await button("Insertar matriz configurable").click();
      await expect(page.getByText(/Elige entre 1 y 8 filas/)).toBeVisible();
      expect(await matrix.evaluate((element) => element.value)).toBe(
        matrixSource,
      );
      await button("Volver al párrafo").click();
      const protectedLatex = String.raw`\newcommand{\matchStudy}[1]{#1^2}
\begin{tikzpicture}\draw[blue] (0,0)--(1,0)--(1,1);\end{tikzpicture}
\begin{unknownEnvironment}Un fragmento conservado.\end{unknownEnvironment}`;
      // Unknown environment is preserved; the compilable fixture defines it explicitly.
      const source =
        String.raw`\newenvironment{unknownEnvironment}{}{}` +
        "\n" +
        protectedLatex;
      await button("Bloque LaTeX avanzado").click();
      await page
        .getByLabel("Código LaTeX protegido", { exact: true })
        .fill(source);
      await button("Conservar bloque").click();
      await button("Fuente LaTeX").click();
      const original = await page
        .getByLabel("Fuente LaTeX", { exact: true })
        .inputValue();
      expect(original).toContain(source);
      expect(original).toContain(matrixSource);
      expect(original).toContain(nested);
      await button("Fuente LaTeX").click();
      await button("Fuente LaTeX").click();
      expect(
        await page.getByLabel("Fuente LaTeX", { exact: true }).inputValue(),
      ).toBe(original);
      await button("Fuente LaTeX").click();
      await page.screenshot({
        path: evidence + "/math-tools-palette-validation.png",
        fullPage: true,
      });
      const viewport = page.locator(".study-document-viewport"),
        toolbar = page.locator(".document-toolbar");
      expect((await toolbar.boundingBox()).height).toBeLessThan(
        (await viewport.boundingBox()).height * 0.6,
      );
      await page.setViewportSize({ width: 480, height: 900 });
      expect((await toolbar.boundingBox()).height).toBeLessThan(
        (await viewport.boundingBox()).height * 0.6,
      );
      expect(
        await page.evaluate(
          () => document.documentElement.scrollWidth <= innerWidth + 1,
        ),
      ).toBe(true);
      await page.screenshot({
        path: evidence + "/math-tools-palette-narrow.png",
        fullPage: true,
      });
      await page.setViewportSize({ width: 1440, height: 1080 });
      await page
        .getByText("Más herramientas matemáticas", { exact: true })
        .click();
      await viewport.evaluate((element) => {
        element.scrollTop = 0;
      });
      await page.screenshot({
        path: evidence + "/math-tools-matrix-nested-tikz.png",
        fullPage: true,
      });
      await page
        .getByLabel("Título de la entrada", { exact: true })
        .fill("Herramientas matemáticas verificadas");
      await button("Guardar entrada").click();
      await expect(page).toHaveURL(/\/study\/notebook\/diary_/u);
      const identity = new URL(page.url()).pathname.split("/").at(-1),
        path = "/notebook/" + identity;
      const saved = await page.evaluate(async (path) => {
        const context = await (await fetch("/api/study/v1/context")).json();
        return (
          await fetch("/api/study/v1" + path, {
            headers: { "X-MathMongo-Library": context.library_id },
          })
        ).json();
      }, path);
      expect(saved.latex_body).toBe(original);
      await coverage.reload();
      await expect(
        page.getByLabel("Título de la entrada", { exact: true }),
      ).toHaveValue("Herramientas matemáticas verificadas");
      await button("Fuente LaTeX").click();
      expect(
        await page.getByLabel("Fuente LaTeX", { exact: true }).inputValue(),
      ).toBe(original);
      await button("Fuente LaTeX").click();
      const pending = page.waitForEvent("download", { timeout: 30000 });
      await button("Exportar PDF").click();
      const pdf = evidence + "/math-tools.pdf";
      await (await pending).saveAs(pdf);
      expect((await readFile(pdf)).subarray(0, 5).toString()).toBe("%PDF-");
      const text = spawnSync("pdftotext", [pdf, "-"], { encoding: "utf8" });
      expect(text.status).toBe(0);
      expect(text.stdout).toContain("fragmento conservado");
      if (process.env.MATHMONGO_LEGACY_CASES) {
        const cases = JSON.parse(
            await readFile(process.env.MATHMONGO_LEGACY_CASES, "utf8"),
          ),
          item = cases.find((entry) => entry.case === "mathematics");
        const read = () =>
          page.evaluate(async (key) => {
            const context = await (await fetch("/api/study/v1/context")).json();
            return (
              await fetch(
                "/api/study/v1/concepts/detail?" + new URLSearchParams({ key }),
                { headers: { "X-MathMongo-Library": context.library_id } },
              )
            ).json();
          }, item.key);
        await coverage.goto(
          base + "/study/concepts/" + encodeURIComponent(item.key),
        );
        const before = await read();
        await page
          .getByRole("link", { name: "Editar concepto", exact: true })
          .click();
        await button("Fuente LaTeX").click();
        const source = page.getByRole("textbox", {
          name: "Fuente LaTeX",
          exact: true,
        });
        await expect(source).toHaveValue(before.contenido_latex);
        const expression = /(?<!\\)\$(?!\$)([^$\n]+)(?<!\\)\$/u.exec(
          before.contenido_latex,
        );
        expect(expression).not.toBeNull();
        const expected =
          before.contenido_latex.slice(0, expression.index) +
          expression[0].slice(0, -1) +
          "+0$" +
          before.contenido_latex.slice(expression.index + expression[0].length);
        await source.fill(expected);
        await button("Guardar concepto").click();
        await expect(
          page.getByRole("heading", { name: item.title, exact: true }),
        ).toBeVisible();
        expect((await read()).contenido_latex).toBe(expected);
        await writeFile(
          evidence + "/math-tools-historical-edit.json",
          JSON.stringify(
            {
              case: item.case,
              key: item.key,
              mode: "source-preserving",
              onlyOneFormulaChanged: true,
              MathV0_writes: 0,
            },
            null,
            2,
          ),
        );
      }
      await writeFile(
        evidence + "/math-tools-browser.json",
        JSON.stringify(
          {
            passed: true,
            browser: name,
            noteId: identity,
            matrixSource,
            nested,
            protectedLatex: source,
            canonicalLatex: original,
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
