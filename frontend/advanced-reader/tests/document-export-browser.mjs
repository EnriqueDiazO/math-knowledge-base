import test from "node:test";
import { chromium, firefox, expect } from "@playwright/test";
import { readFile, writeFile } from "node:fs/promises";
import { spawnSync } from "node:child_process";
import { browserCoverage } from "./browser-coverage.mjs";

await test(
  "visual academic document and mixed protected LaTeX export to real PDF",
  { timeout: 150000 },
  async () => {
    const name = process.env.MATHMONGO_STUDY_BROWSER ?? "chrome",
      base = process.env.MATHMONGO_INDEPENDENT_URL,
      evidence = process.env.MATHMONGO_INDEPENDENT_EVIDENCE;
    const authoring = JSON.parse(
      await readFile(evidence + "/authoring-browser.json", "utf8"),
    );
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
    const coverage = await browserCoverage(page, name, "document-export");
    let passed = false;
    const errors = [];
    page.on("pageerror", (error) => errors.push(error.message));
    const advanced = String.raw`\newcommand{\keptMacro}[1]{\textbf{#1}}
\keptMacro{Texto avanzado protegido}
\begin{tikzpicture}
\draw[blue,thick] (0,0)--(2,1);
\node at (1,0.8) {A};
\end{tikzpicture}`;
    const read = (key) =>
      page.evaluate(async (key) => {
        const scope = await (await fetch("/api/study/v1/context")).json();
        return (
          await fetch(
            "/api/study/v1/concepts/detail?" + new URLSearchParams({ key }),
            { headers: { "X-MathMongo-Library": scope.library_id } },
          )
        ).json();
      }, key);
    const download = async (label, filename) => {
      const event = page.waitForEvent("download");
      await page.getByRole("button", { name: label, exact: true }).click();
      const file = await event;
      await file.saveAs(evidence + "/" + filename);
      return evidence + "/" + filename;
    };
    try {
      await coverage.goto(
        base +
          "/study/concepts/new?" +
          new URLSearchParams({ source: authoring.sourceId }),
      );
      await page
        .getByLabel("Nombre del concepto", { exact: true })
        .fill("Documento académico visual");
      await page
        .getByRole("combobox", {
          name: "Insertar bloque de estudio",
          exact: true,
        })
        .selectOption("context");
      await page
        .locator('[data-study-block="context"] p')
        .last()
        .fill("Contexto creado visualmente.");
      await page
        .getByRole("combobox", {
          name: "Insertar bloque de resultado",
          exact: true,
        })
        .selectOption("definition");
      await page
        .locator('[data-result="definition"] p')
        .last()
        .fill("Definición visual con fórmula.");
      await page
        .getByRole("button", { name: "Insertar fórmula en línea", exact: true })
        .click();
      await page
        .locator("math-field")
        .last()
        .evaluate((field) => {
          field.value = String.raw`\frac{1}{2}`;
          field.dispatchEvent(new InputEvent("input", { bubbles: true }));
        });
      await page
        .getByRole("button", { name: "Volver al párrafo", exact: true })
        .click();
      await page
        .getByRole("button", { name: "Bloque LaTeX avanzado", exact: true })
        .click();
      await page
        .getByLabel("Código LaTeX protegido", { exact: true })
        .fill(advanced);
      await page
        .getByRole("button", { name: "Conservar bloque", exact: true })
        .click();
      await page.screenshot({
        path: evidence + "/document-visual-structured-editor.png",
        fullPage: true,
      });
      const writes = [];
      const observeWrites = request => {
        if (request.url().endsWith("/operations") && request.method() === "POST") writes.push(request.url());
      };
      page.on("request", observeWrites);
      await page.getByRole("button", {name:"Vista compilada", exact:true}).click();
      const compiledPage = page.getByRole("img", {name:"Primera página del borrador compilado", exact:true});
      await expect(compiledPage).toBeVisible();
      await expect.poll(() => compiledPage.evaluate(image => image.naturalWidth)).toBeGreaterThan(0);
      const draftPdf = await download("Descargar borrador PDF", "document-unsaved-draft.pdf");
      const draftText = spawnSync("pdftotext", [draftPdf, "-"], {encoding:"utf8"});
      expect(draftText.status).toBe(0);
      expect(draftText.stdout).toContain("Contexto creado visualmente");
      expect(draftText.stdout).toContain("Texto avanzado protegido");
      expect(writes).toEqual([]);
      await page.screenshot({path:evidence + "/document-unsaved-compiled-wide.png",fullPage:true});
      await page.setViewportSize({width:700,height:960});
      expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1)).toBe(true);
      await page.screenshot({path:evidence + "/document-unsaved-compiled-narrow.png",fullPage:true});
      await page.setViewportSize({width:1440,height:1080});
      page.off("request", observeWrites);
      await page
        .getByRole("button", { name: "Guardar concepto", exact: true })
        .click();
      await expect(
        page.getByRole("heading", {
          name: "Documento académico visual",
          exact: true,
        }),
      ).toBeVisible();
      const key = decodeURIComponent(
          new URL(page.url()).pathname.split("/").at(-1),
        ),
        before = await read(key);
      expect(before.contenido_latex).toContain("\\begin{context}\n");
      expect(before.contenido_latex).toContain("\\begin{definition}{}\n");
      expect(before.contenido_latex).toContain(advanced);
      const firstPdf = await download("Exportar PDF", "document-visual.pdf");
      expect((await readFile(firstPdf)).subarray(0, 5).toString()).toBe(
        "%PDF-",
      );
      const text = spawnSync("pdftotext", [firstPdf, "-"], {
        encoding: "utf8",
      });
      expect(text.status).toBe(0);
      expect(text.stdout).toContain("Contexto creado visualmente");
      expect(text.stdout).toContain("Texto avanzado protegido");
      expect(text.stdout).not.toContain("ID del concepto:");
      await page.getByRole("checkbox", {name:"Incluir identificadores técnicos",exact:true}).check();
      const tracedPdf = await download("Exportar PDF", "document-traceability.pdf");
      const tracedText = spawnSync("pdftotext", [tracedPdf, "-"], {encoding:"utf8"});
      expect(tracedText.status).toBe(0);
      expect(tracedText.stdout).toContain("ID del concepto:");
      await page.getByRole("checkbox", {name:"Incluir identificadores técnicos",exact:true}).uncheck();
      const block = page
        .locator("[data-source-block]")
        .filter({ hasText: "tikzpicture" })
        .first();
      await block.locator("summary").click();
      await block
        .getByRole("button", { name: "Ver figura", exact: true })
        .click();
      await expect(
        block.getByRole("img", {
          name: "Vista previa de la figura LaTeX",
          exact: true,
        }),
      ).toBeVisible();
      await expect(block.getByRole("img")).toHaveJSProperty("complete", true);
      await expect.poll(() => block.getByRole("img").evaluate(image => image.naturalWidth)).toBeGreaterThan(0);
      await block
        .getByRole("button", { name: "Ampliar figura", exact: true })
        .click();
      await expect(page.locator(".figure-preview-dialog")).toBeVisible();
      await page.screenshot({ path: evidence + "/document-tikz-preview.png" });
      await page
        .getByRole("button", { name: "Cerrar figura", exact: true })
        .click();
      await page
        .getByRole("link", { name: "Editar concepto", exact: true })
        .click();
      await page
        .locator('[data-study-block="context"] p')
        .first()
        .fill("Contexto corregido visualmente.");
      await page
        .getByRole("button", { name: "Guardar concepto", exact: true })
        .click();
      await expect(
        page.getByRole("heading", {
          name: "Documento académico visual",
          exact: true,
        }),
      ).toBeVisible();
      const after = await read(key);
      expect(after.contenido_latex).toContain(advanced);
      expect(after.contenido_latex).toContain(
        "Contexto corregido visualmente.",
      );
      const zip = await download(
        "Exportar proyecto TEX",
        "document-mixed-tex.zip",
      );
      const raw = spawnSync("unzip", ["-p", zip, "*/content/body.tex"], {
        encoding: "utf8",
      });
      expect(raw.status).toBe(0);
      expect(raw.stdout).toBe(after.contenido_latex);
      await download("Exportar PDF", "document-mixed.pdf");
      expect(errors).toEqual([]);
      passed = true;
      await writeFile(
        evidence + "/document-export-browser.json",
        JSON.stringify(
          {
            passed,
            browser: name,
            version: browser.version(),
            key,
            sourceId: authoring.sourceId,
            visualPdf: true,
            unsavedDraftCompiledWithoutWrite: true,
            optionalTechnicalIds: true,
            narrowViewport: 700,
            mixedProtectedLatexPreserved: true,
            errors,
          },
          null,
          2,
        ),
      );
    } finally {
      await coverage.finish(passed);
      await browser.close();
    }
  },
);
