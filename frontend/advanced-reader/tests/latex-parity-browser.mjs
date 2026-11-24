import test from "node:test";
import { chromium, firefox, expect } from "@playwright/test";
import { readFile, writeFile } from "node:fs/promises";
import { spawnSync } from "node:child_process";
import { createHash } from "node:crypto";
import { browserCoverage } from "./browser-coverage.mjs";
import { readSource, writeSource, sourceField } from "./source-browser.mjs";

await test(
  "complete LaTeX authoring corpus, diagnostics and two-window recovery",
  { timeout: 600000 },
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
    const context = await browser.newContext({
        viewport: { width: 1440, height: 1080 },
        reducedMotion: "reduce",
      }),
      page = await context.newPage();
    const coverage = await browserCoverage(page, name, "latex-parity"),
      errors = [];
    page.on("pageerror", (error) => errors.push(error.message));
    await page.addInitScript(() => {
      window.mathmongoStyleViolations = [];
      document.addEventListener("securitypolicyviolation", (event) => {
        if (event.effectiveDirective.startsWith("style-src"))
          window.mathmongoStyleViolations.push(
            event.effectiveDirective + ":" + event.blockedURI,
          );
      });
    });

    const codeRequests = [];
    page.on("request", (request) => {
      if (/source-editor-[^/]+\.js$/u.test(new URL(request.url()).pathname))
        codeRequests.push(request.url());
    });
    const cases = JSON.parse(
        await readFile(process.env.MATHMONGO_LATEX_CORPUS, "utf8"),
      ),
      results = [];
    let passed = false;
    const button = (label) =>
      page.getByRole("button", { name: label, exact: true });
    const read = (key, target = page) =>
      target.evaluate(async (key) => {
        const context = await (await fetch("/api/study/v1/context")).json();
        const response = await fetch(
          "/api/study/v1/concepts/detail?" + new URLSearchParams({ key }),
          { headers: { "X-MathMongo-Library": context.library_id } },
        );
        if (!response.ok) throw new Error("Could not read saved concept");
        return response.json();
      }, key);
    const compile = async (expected = "ready") => {
      await button("Vista compilada").click();
      const panel = page.locator(".document-compiled-preview .figure-preview");
      if (expected === "ready") {
        await expect(panel.locator("img")).toBeVisible({ timeout: 30000 });
        await expect
          .poll(
            () => panel.locator("img").evaluate((image) => image.naturalWidth),
            { timeout: 10000 },
          )
          .toBeGreaterThan(0);
      } else {
        await expect(panel.getByRole("status")).toContainText(
          "no está definido",
          { timeout: 30000 },
        );
        await panel
          .getByText("Detalles de compilación", { exact: true })
          .click();
        await expect(panel.locator("pre")).toContainText("concept undefined");
      }
    };
    const exportProject = async (prefix, expected) => {
      const download = page.waitForEvent("download");
      await button("Exportar proyecto TEX").click();
      const path = evidence + "/" + prefix + ".zip";
      await (await download).saveAs(path);
      const extracted = spawnSync(
        "python3",
        [
          "-c",
          "import sys,zipfile; z=zipfile.ZipFile(sys.argv[1]); sys.stdout.buffer.write(z.read(next(n for n in z.namelist() if n.endswith('/content/body.tex'))))",
          path,
        ],
        { encoding: "utf8", maxBuffer: 1_000_000 },
      );
      expect(extracted.status).toBe(0);
      expect(extracted.stdout).toBe(expected);
    };
    try {
      for (const item of cases) {
        const original = await readFile(item.path, "utf8");
        expect(createHash("sha256").update(original).digest("hex")).toBe(
          item.sha256,
        );
        await coverage.goto(
          base + "/study/concepts/" + encodeURIComponent(item.key) + "/edit",
        );
        await expect(
          page.getByRole("heading", { name: "Editar concepto", exact: true }),
        ).toBeVisible();
        if (item.case === 1) expect(codeRequests).toHaveLength(0);
        await button("Fuente LaTeX").click();
        expect(await readSource(page)).toBe(original);
        if (item.case === 1) expect(codeRequests).toHaveLength(1);
        if (item.case === 1) {
          const layout = await sourceField(page).evaluate((element) => {
            const root = element.getRootNode(),
              view = element.closest(".cm-editor");
            return {
              shadow: root instanceof ShadowRoot,
              sheets:
                root instanceof ShadowRoot ? root.adoptedStyleSheets.length : 0,
              font: getComputedStyle(view.querySelector(".cm-scroller"))
                .fontFamily,
              gutter: getComputedStyle(view.querySelector(".cm-gutters"))
                .position,
              violations: window.mathmongoStyleViolations,
            };
          });
          expect(layout.shadow).toBe(true);
          expect(layout.sheets).toBeGreaterThanOrEqual(2);
          expect(layout.font).toContain("monospace");
          expect(layout.gutter).toBe("sticky");
          expect(layout.violations).toEqual([]);
          await expect(
            page.getByRole("group", {
              name: "Texto y estructura",
              exact: true,
            }),
          ).toBeHidden();
          const overlap = await page
            .locator(".study-document-actions")
            .evaluate((element) => {
              const surface = document.querySelector(
                ".study-document-viewport",
              );
              return {
                position: getComputedStyle(element).position,
                top: element.getBoundingClientRect().top,
                bottom: surface.getBoundingClientRect().bottom,
                zoom: visualViewport.scale,
              };
            });
          expect(overlap.position).toBe("static");
          expect(overlap.top).toBeGreaterThanOrEqual(overlap.bottom);
          expect(overlap.zoom).toBe(1);
          await writeFile(
            evidence + "/source-style-policy.json",
            JSON.stringify(layout, null, 2),
          );
        }

        await writeSource(page, original);
        expect(await readSource(page)).toBe(original);
        await button("Fuente LaTeX").click();
        await button("Fuente LaTeX").click();
        expect(await readSource(page)).toBe(original);
        await compile(item.case === 4 ? "undefined-environment" : "ready");
        expect(await readSource(page)).toBe(original);
        if (item.case === 10) {
          expect(item.lines).toBeGreaterThanOrEqual(200);
          await page.getByLabel("Ir a línea", { exact: true }).fill("200");
          await button("Ir").click();
          await expect(page.locator(".cm-activeLineGutter")).toHaveText("200");
          await page.screenshot({
            path: evidence + "/latex-source-325-lines.png",
            fullPage: true,
          });
        }
        await button("Guardar concepto").click();
        await expect(
          page.getByRole("heading", { name: item.title, exact: true }),
        ).toBeVisible();
        expect((await read(item.key)).contenido_latex).toBe(original);
        await exportProject("latex-case-" + item.case, original);
        if (item.case !== 4) {
          const pdf = page.waitForEvent("download");
          await button("Exportar PDF").click();
          const path = evidence + "/latex-case-" + item.case + ".pdf";
          await (await pdf).saveAs(path);
          expect((await readFile(path)).subarray(0, 5).toString()).toBe(
            "%PDF-",
          );
          const text = spawnSync("pdftotext", [path, "-"], {
            encoding: "utf8",
          });
          expect(text.status).toBe(0);
          expect(text.stdout.trim().length).toBeGreaterThan(30);
        } else {
          await button("Exportar PDF").click();
          await expect(
            page.locator(".study-export-actions [role=status]"),
          ).toContainText("no está definido", { timeout: 30000 });
          expect((await read(item.key)).contenido_latex).toBe(original);
        }

        await coverage.reload();
        expect((await read(item.key)).contenido_latex).toBe(original);
        results.push({
          case: item.case,
          sha256: item.sha256,
          lines: item.lines,
          exact: true,
          compilation:
            item.case === 4
              ? "requires-original-environment-definitions"
              : "ready",
        });
      }
      // Localized historic edit changes only the chosen phrase, not its figure or macros.
      const historical = cases.find((item) => item.case === 4),
        raw = await readFile(historical.path, "utf8");
      const phrase = "Se estudia",
        position = raw.indexOf(phrase);
      expect(position).toBeGreaterThan(0);
      const edited =
        raw.slice(0, position) +
        "Se analiza" +
        raw.slice(position + phrase.length);
      await coverage.goto(
        base +
          "/study/concepts/" +
          encodeURIComponent(historical.key) +
          "/edit",
      );
      await button("Fuente LaTeX").click();
      await writeSource(page, edited);
      await button("Guardar concepto").click();
      await expect(
        page.getByRole("heading", { name: historical.title, exact: true }),
      ).toBeVisible();
      expect((await read(historical.key)).contenido_latex).toBe(edited);
      // Context is explicitly authored by the test; it is not claimed to be the lost original preamble.
      const explicit =
        String.raw`\documentclass{notes}
\newenvironment{concept}[1]{\section*{#1}}{}
\newenvironment{reference}{\begin{quote}\small}{\end{quote}}
\begin{document}
` +
        raw +
        "\n\\end{document}\n";
      await coverage.goto(
        base +
          "/study/concepts/" +
          encodeURIComponent(historical.key) +
          "/edit",
      );
      await button("Fuente LaTeX").click();
      await writeSource(page, explicit);
      await compile();
      const helicoidalPdf = page.waitForEvent("download");
      await button("Descargar borrador PDF").click();
      await (
        await helicoidalPdf
      ).saveAs(evidence + "/helicoidal-explicit-context.pdf");
      await page.screenshot({
        path: evidence + "/helicoidal-explicit-compiled.png",
        fullPage: true,
      });
      // Leave the historical source as its localized edit, without saving the extra context.
      await writeSource(page, edited);
      // Create a complete new document using the same source surface and actual persistence.
      const complete = await readFile(
        cases.find((item) => item.case === 9).path,
        "utf8",
      );
      await coverage.goto(
        base +
          "/study/concepts/new?source=" +
          process.env.MATHMONGO_PALETTE_SOURCE,
      );
      await page
        .getByLabel("Nombre del concepto", { exact: true })
        .fill("Documento completo creado desde React");
      await button("Fuente LaTeX").click();
      await writeSource(page, complete);
      await button("Guardar concepto").click();
      await expect(
        page.getByRole("heading", {
          name: "Documento completo creado desde React",
          exact: true,
        }),
      ).toBeVisible();
      const key = decodeURIComponent(
        new URL(page.url()).pathname.split("/").at(-1),
      );
      expect((await read(key)).contenido_latex).toBe(complete);
      await page
        .getByRole("link", { name: "Editar concepto", exact: true })
        .click();
      await button("Fuente LaTeX").click();
      // Completion, paired environments and resizing are actual source-editor actions.
      await sourceField(page).press("ControlOrMeta+End");
      await page.keyboard.insertText("\n\\fra");
      await sourceField(page).press("ControlOrMeta+Space");
      const completion = page
        .locator('.cm-tooltip-autocomplete [role="option"]')
        .filter({ hasText: "\\frac" });
      await expect(completion).toHaveCount(1);
      await completion.click();
      await page.keyboard.insertText("1");
      await sourceField(page).press("Tab");
      await page.keyboard.insertText("2");
      expect(await readSource(page)).toContain(String.raw`\frac{1}{2}`);
      await writeSource(page, complete);
      await sourceField(page).press("ControlOrMeta+End");
      await page
        .getByLabel("Insertar fragmento LaTeX", { exact: true })
        .selectOption("definition");
      const paired = await readSource(page);
      expect(paired).toContain(String.raw`\begin{definition}{Título}`);
      expect(paired).toContain(String.raw`\end{definition}`);
      await writeSource(page, complete);
      await page
        .getByLabel("Altura del código", { exact: true })
        .selectOption("20rem");
      await expect
        .poll(() =>
          page
            .locator(".latex-source-viewport")
            .evaluate((el) => getComputedStyle(el).height),
        )
        .toBe("320px");

      // Find, replace and undo/redo execute the installed CodeMirror UI on complete source.
      await button("Buscar y reemplazar").click();
      await page.locator('.cm-search input[name="search"]').fill("Trabajamos");
      await page
        .locator('.cm-search input[name="replace"]')
        .fill("Investigamos");
      await page.locator('.cm-search button[name="replaceAll"]').click();
      const replaced = complete.replaceAll("Trabajamos", "Investigamos");
      expect(await readSource(page)).toBe(replaced);
      await button("Deshacer código").click();
      expect(await readSource(page)).toBe(complete);
      await button("Rehacer código").click();
      expect(await readSource(page)).toBe(replaced);
      await writeSource(page, complete);
      // Unknown macro failure is actionable and never publishes the broken draft.
      const broken = complete.replace(
        "\\end{document}",
        "\\macroDePruebaNoDefinida\n\\end{document}",
      );
      await writeSource(page, broken);
      await button("Vista compilada").click();
      await expect(page.locator(".figure-preview [role=status]")).toContainText(
        "sin definir",
        { timeout: 30000 },
      );
      expect((await read(key)).contenido_latex).toBe(complete);
      expect(await readSource(page)).toBe(broken);
      // TikZ is compiled twice after a localized edit, then exported and saved.
      const tikz = String.raw`\begin{tikzpicture}\draw[blue,thick] (0,0)--(2,0)--(2,1);\end{tikzpicture}`;
      let mixed = complete.replace(
        "\\end{document}",
        tikz + "\n\\end{document}",
      );
      await writeSource(page, mixed);
      await compile();
      mixed = mixed.replace("draw[blue,thick]", "draw[red,thick]");
      await writeSource(page, mixed);
      await compile();
      const pdf = page.waitForEvent("download");
      await button("Descargar borrador PDF").click();
      await (await pdf).saveAs(evidence + "/complete-source-tikz.pdf");
      await page.setViewportSize({ width: 480, height: 900 });
      expect(
        await page.evaluate(
          () => document.documentElement.scrollWidth <= innerWidth + 1,
        ),
      ).toBe(true);
      await page.screenshot({
        path: evidence + "/latex-source-narrow.png",
        fullPage: true,
      });
      await page.setViewportSize({ width: 1440, height: 1080 });
      await button("Guardar concepto").click();
      await expect(
        page.getByRole("heading", {
          name: "Documento completo creado desde React",
          exact: true,
        }),
      ).toBeVisible();
      await exportProject("complete-source-tikz", mixed);
      // Two actual tabs share localStorage. A successful save must not erase the other draft.
      const other = await context.newPage();
      await coverage.goto(
        base + "/study/concepts/" + encodeURIComponent(key) + "/edit",
      );
      await other.goto(
        base + "/study/concepts/" + encodeURIComponent(key) + "/edit",
      );
      await button("Fuente LaTeX").click();
      const local = mixed.replace(
        "Trabajamos",
        "Mi contribución local: trabajamos",
      );
      await writeSource(page, local);
      await other
        .getByLabel("Nombre del concepto", { exact: true })
        .fill("Versión de otra ventana");
      await other
        .getByRole("button", { name: "Guardar concepto", exact: true })
        .click();
      await expect(
        other.getByRole("heading", {
          name: "Versión de otra ventana",
          exact: true,
        }),
      ).toBeVisible();
      await coverage.reload();
      await expect(sourceField(page)).toBeVisible();
      expect(await readSource(page)).toBe(local);
      await button("Guardar concepto").click();
      await expect(
        page.getByText("Otra ventana cambió el concepto.", { exact: false }),
      ).toBeVisible();
      expect((await read(key)).contenido_latex).toBe(mixed);
      await button("Consultar versión guardada").click();
      await expect(
        page.getByRole("heading", {
          name: "Versión guardada: Versión de otra ventana",
          exact: true,
        }),
      ).toBeVisible();
      await button("Combinar mi borrador sobre esta revisión").click();
      await expect(
        page.getByLabel("Nombre del concepto", { exact: true }),
      ).toHaveValue("Versión de otra ventana");
      expect(await readSource(page)).toBe(local);
      expect((await read(key)).contenido_latex).toBe(mixed);
      await button("Guardar concepto").click();
      await expect(
        page.getByRole("heading", {
          name: "Versión de otra ventana",
          exact: true,
        }),
      ).toBeVisible();
      expect((await read(key)).contenido_latex).toBe(local);
      await other.close();
      expect(errors).toEqual([]);
      await writeFile(
        evidence + "/latex-parity-browser.json",
        JSON.stringify(
          {
            passed: true,
            browser: name,
            cases: results,
            createdKey: key,
            canonicalLatex: local,
            historicalLocalized: true,
            concurrentExplicitRecovery: true,
            streamlit_started: false,
            MathV0_writes: 0,
          },
          null,
          2,
        ),
      );
      passed = true;
    } catch (error) {
      await page
        .screenshot({
          path: evidence + "/latex-parity-failure.png",
          fullPage: true,
        })
        .catch(() => {});
      throw error;
    } finally {
      await coverage.finish(passed);
      await browser.close();
    }
  },
);
