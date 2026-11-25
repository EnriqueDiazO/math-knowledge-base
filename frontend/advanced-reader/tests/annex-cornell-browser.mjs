/** Historical Cornell: three simultaneous editors, independent saves, draft recovery and exports. */
import test from "node:test";
import { browserCoverage } from "./browser-coverage.mjs";
import { chromium, firefox, expect } from "@playwright/test";
import { mkdir, readFile, writeFile } from "node:fs/promises";
import { resolve } from "node:path";
import { readSource, writeSource } from "./source-browser.mjs";
await test(
  "three Cornell regions retain independent content and local selections",
  { timeout: 300000 },
  async () => {
    const root = resolve("../../evidence/sonar/cpi-five-images-2026-11-24"),
      own = JSON.parse(
        await readFile(resolve(root, "owned-comparison.json"), "utf8"),
      ),
      name = process.env.MATHMONGO_STUDY_BROWSER || "chrome",
      phase = process.env.MATHMONGO_ANNEX_PHASE || "after",
      base =
        phase === "before" ? own.cornell_baseline.url : own.instances.react.url,
      out = resolve(root, "cornell-ui-" + phase + "-" + name),
      id = "6a4d7d2b467f981c3741eb8c";
    await mkdir(out, { recursive: true });
    const browser =
        name === "firefox"
          ? await firefox.launch({ headless: true })
          : await chromium.launch({
              headless: true,
              executablePath: "/usr/bin/google-chrome",
              args: ["--no-sandbox"],
            }),
      context = await browser.newContext({
        viewport: { width: 1600, height: 1100 },
        recordVideo: { dir: out, size: { width: 1600, height: 1100 } },
        reducedMotion: "reduce",
      }),
      page = await context.newPage(),
      proof = { phase, browser: name, events: [], errors: [] },
      start = Date.now();
    process.env.MATHMONGO_INDEPENDENT_EVIDENCE = out;
    process.env.MATHMONGO_INDEPENDENT_URL = base;
    const coverage = await browserCoverage(page, name, "annex-cornell");
    page.on("pageerror", (error) => proof.errors.push(error.message));
    proof.network = [];
    page.on("response", (response) => {
      if (response.status() >= 400)
        proof.network.push({ url: response.url(), status: response.status() });
    });
    page.setDefaultTimeout(30000);
    const mark = async (label) => {
      proof.events.push({ seconds: (Date.now() - start) / 1000, label });
      await page.screenshot({
        path: resolve(out, "step-" + proof.events.length + ".png"),
        fullPage: true,
        timeout: 20000,
      });
      await page.waitForTimeout(600);
    };
    const request = (path) =>
      page.evaluate(async (path) => {
        const ctx = await (await fetch("/api/study/v1/context")).json();
        return (
          await fetch("/api/study/v1" + path, {
            headers: { "X-MathMongo-Library": ctx.library_id },
          })
        ).json();
      }, path);
    const opened = () => request("/structured/cornell/" + id),
      panel = (key) => page.locator(".cornell-region-" + key),
      keys = ["cue", "main", "summary"];
    const source = async (key) => {
      const p = panel(key);
      const toggle = p.getByRole("button", {
        name: "Fuente LaTeX",
        exact: true,
      });
      if ((await toggle.getAttribute("aria-pressed")) !== "true")
        await toggle.click();
      await p
        .getByRole("textbox", { name: "Fuente LaTeX", exact: true })
        .waitFor();
      return p;
    };
    const save = async () => {
      await page
        .getByRole("button", { name: "Guardar nota Cornell", exact: true })
        .click();
      await expect(
        page.getByText("Nota guardada y confirmada en esta biblioteca.", {
          exact: true,
        }),
      ).toBeVisible();
      await coverage.reload();
      await expect(
        page.getByRole("heading", { name: "Editar nota Cornell", exact: true }),
      ).toBeVisible();
    };
    try {
      await coverage.goto(base + "/study/notebook/cornell/" + id);
      await expect(
        page.getByRole("heading", { name: "Editar nota Cornell", exact: true }),
      ).toBeVisible();
      const original = await opened();
      const pristine = JSON.parse(
        await readFile(resolve(root, "annex-cornell-private.json"), "utf8"),
      ).note.cornell;
      proof.initial_revision = original.revision;
      proof.initial_regions = original.document.pages[0];
      if (phase === "before") {
        expect(await page.locator(".document-composer").count()).toBe(1);
        await mark(
          "One editor alternating three existing model regions; original Cornell before",
        );
      } else {
        await expect(page.locator(".cornell-region")).toHaveCount(3);
        for (const key of keys) {
          await expect(
            panel(key).getByRole("heading", { level: 2 }),
          ).toBeVisible();
          await writeSource(
            await source(key),
            pristine.pages[0][key].latex +
              "\n" +
              key.toUpperCase() +
              " " +
              name +
              " 1.",
          );
        }
        await mark(
          "Three historical regions, permanent labels and independent source editors",
        );
        await save();
        for (const key of keys) {
          const before = await opened();
          await writeSource(
            await source(key),
            before.document.pages[0][key].latex.replace(
              key.toUpperCase() + " " + name + " 1.",
              key.toUpperCase() + " " + name + " 2.",
            ),
          );
          await save();
          const after = await opened();
          for (const other of keys.filter((x) => x !== key))
            expect(after.document.pages[0][other]).toEqual(
              before.document.pages[0][other],
            );
          expect(after.document.pages[0][key].latex).toContain(
            key.toUpperCase() + " " + name + " 2.",
          );
          await mark(
            "Only " +
              key +
              " edited, saved and reloaded; two other regions identical",
          );
        }
        const beforeTools = await opened(),
          main = panel("main");
        await main
          .getByRole("button", { name: "Fuente LaTeX", exact: true })
          .click();
        const visual = main.locator(".visual-document .tiptap");
        await visual.click();
        await visual.press("ControlOrMeta+End");
        await main
          .getByRole("button", {
            name: "Insertar fórmula en línea",
            exact: true,
          })
          .click();
        await main
          .locator("math-field")
          .last()
          .evaluate((field) => {
            field.value = String.raw`\frac{a}{b}`;
            field.dispatchEvent(new InputEvent("input", { bubbles: true }));
          });
        await main
          .getByRole("button", { name: "Volver al párrafo", exact: true })
          .click();
        const choices = await request("/choices");
        let selected;
        for (const item of choices.sources) {
          const refs = await request(
            "/sources/" + encodeURIComponent(item.id) + "/references",
          );
          if (refs.items?.length) {
            selected = { source: item.id, reference: refs.items[0] };
            break;
          }
        }
        expect(selected).toBeTruthy();
        await page
          .getByText("Insertar referencia bibliográfica", { exact: true })
          .click();
        await page
          .getByRole("combobox", { name: "Fuente administrada", exact: true })
          .selectOption(selected.source);
        await page
          .getByRole("combobox", {
            name: "Referencia bibliográfica",
            exact: true,
          })
          .selectOption(selected.reference.reference_id);
        await page
          .getByRole("button", {
            name: "Insertar cita en esta región",
            exact: true,
          })
          .click();
        await expect(
          page.getByText(
            "Cita incorporada al borrador; guarda para conservarla en la biblioteca.",
            { exact: true },
          ),
        ).toBeVisible();
        await main
          .getByRole("button", { name: "Deshacer texto", exact: true })
          .click();
        await expect(main.locator(".visual-document")).not.toContainText(
          selected.reference.title,
        );
        await main
          .getByRole("button", { name: "Rehacer texto", exact: true })
          .click();
        await expect(main.locator(".visual-document")).toContainText(
          selected.reference.title,
        );
        await save();
        const tools = await opened();
        expect(tools.document.pages[0].main.latex).toContain(
          String.raw`\frac{a}{b}`,
        );
        expect(tools.document.pages[0].main.latex).toContain(
          selected.reference.title,
        );
        for (const key of ["cue", "summary"])
          expect(tools.document.pages[0][key]).toEqual(
            beforeTools.document.pages[0][key],
          );
        await mark(
          "Formula and citation stay in Desarrollo; other two regions untouched",
        );
        const beforeDraft = await opened();
        await writeSource(
          await source("cue"),
          beforeDraft.document.pages[0].cue.latex +
            "\n\nBORRADOR RECUPERABLE " +
            name,
        );
        await coverage.reload();
        await expect(
          page.getByRole("heading", {
            name: "Editar nota Cornell",
            exact: true,
          }),
        ).toBeVisible();
        expect((await opened()).revision).toBe(beforeDraft.revision);
        expect(await readSource(await source("cue"))).toContain(
          "BORRADOR RECUPERABLE " + name,
        );
        await mark("Local draft recovered after reload without publishing it");
        await save();
        for (const [label, extension] of [
          ["Exportar proyecto TEX", "zip"],
          ["Exportar PDF", "pdf"],
        ]) {
          const download = page.waitForEvent("download", { timeout: 120000 });
          await page.getByRole("button", { name: label, exact: true }).click();
          await (await download).saveAs(resolve(out, "Cornell." + extension));
          await mark(label + " with three saved regions");
        }
        await page.setViewportSize({ width: 600, height: 1000 });
        await expect(page.locator(".cornell-region")).toHaveCount(3);
        const geometry = await page
          .locator(".cornell-region")
          .evaluateAll((nodes) =>
            nodes.map((node) => ({
              x: node.getBoundingClientRect().x,
              width: node.getBoundingClientRect().width,
            })),
          );
        expect(geometry[0].x).toBe(geometry[1].x);
        expect(geometry[1].x).toBe(geometry[2].x);
        await mark(
          "Narrow screen stacks the same three labeled editable regions",
        );
        proof.final_revision = (await opened()).revision;
      }
      proof.passed = true;
    } catch (error) {
      proof.passed = false;
      proof.error = String(error);
      await page
        .screenshot({
          path: resolve(out, "failed.png"),
          fullPage: true,
          timeout: 20000,
        })
        .catch(() => {});
      throw error;
    } finally {
      await coverage.finish(proof.passed === true);
      await page.close();
      await page.video().saveAs(resolve(out, "Cornell.webm"));
      await writeFile(
        resolve(out, "browser.json"),
        JSON.stringify(proof, null, 2),
      );
      await context.close();
      await browser.close();
    }
  },
);
