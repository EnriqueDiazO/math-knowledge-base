import { browserCoverage } from "./browser-coverage.mjs";
import { chromium, firefox, expect } from "@playwright/test";
import { writeFile } from "node:fs/promises";
import test from "node:test";

await test(
  "independent study persistence and return to passage",
  { timeout: 150000 },
  async () => {
    const name = process.env.MATHMONGO_STUDY_BROWSER ?? "chrome";
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
    });
    const page = await context.newPage();
    const coverage = await browserCoverage(page, name, "reading");
    let passed = false;
    page.setDefaultTimeout(20000);
    const evidence = process.env.MATHMONGO_INDEPENDENT_EVIDENCE,
      base = process.env.MATHMONGO_INDEPENDENT_URL;
    const errors = [],
      outside = [];
    page.on("pageerror", (error) => errors.push(error.message));
    page.on("request", (request) => {
      if (
        !["127.0.0.1", "localhost"].includes(new URL(request.url()).hostname) &&
        !request.url().startsWith("data:") &&
        !request.url().startsWith("blob:")
      )
        outside.push(request.url());
    });
    const progress = async (value) =>
      writeFile(evidence + "/progress.log", value + "\n", { flag: "a" });
    try {
      await coverage.goto(base + "/study/library");
      await expect(
        page.getByRole("heading", { name: "Tu biblioteca" }),
      ).toBeVisible();
      await expect(
        page.getByRole("button", { name: "Preparar notas y subrayados" }),
      ).toBeVisible();
      await page
        .getByRole("button", { name: "Preparar notas y subrayados" })
        .click();
      await expect(
        page.getByRole("status").filter({ hasText: "Función preparada" }),
      ).toBeVisible();
      await expect(
        page.getByRole("button", { name: "Preparar notas y subrayados" }),
      ).toHaveCount(0);
      await page.screenshot({ path: evidence + "/library.png" });
      await page
        .getByRole("link", { name: "Abrir fuente y documentos" })
        .click();
      await page.getByRole("link", { name: "Leer documento" }).click();
      const text = page
        .locator('.page[data-page-number="1"] .textLayer span')
        .first();
      await expect(text).toBeVisible({ timeout: 30000 });
      const selectedText = await text.evaluate((element) => {
        const range = document.createRange();
        range.selectNodeContents(element);
        const selection = window.getSelection();
        selection.removeAllRanges();
        selection.addRange(range);
        element.dispatchEvent(new PointerEvent("pointerup", { bubbles: true }));
        document.dispatchEvent(new Event("selectionchange"));
        return element.textContent;
      });
      await expect(page.locator(".selection-action-toolbar")).toBeVisible();
      await expect(
        page.getByRole("button", {
          name: "Escribir nota desde este pasaje",
          exact: true,
        }),
      ).toBeVisible();
      await page.screenshot({ path: evidence + "/reading-passage.png" });
      await page
        .getByRole("button", {
          name: "Escribir nota desde este pasaje",
          exact: true,
        })
        .click();
      await expect(
        page.getByRole("heading", { name: "Escribir nota" }),
      ).toBeVisible();
      await expect(page.locator(".study-passage blockquote")).toHaveText(
        selectedText,
      );
      await page
        .getByLabel("Nombre de la nota", { exact: true })
        .fill("Una nota desde el frontend independiente");
      const editor = page.locator(".visual-document .tiptap");
      await editor.fill(
        "Una idea matemática que permanece después de recargar.",
      );
      await page
        .getByRole("button", { name: "Insertar fórmula en línea", exact: true })
        .click();
      const math = page.locator("math-field").last();
      await math.evaluate((element) => {
        element.value = "\\frac{1}{2}";
        element.dispatchEvent(new InputEvent("input", { bubbles: true }));
      });
      await math.locator('[part="virtual-keyboard-toggle"]').click();
      await expect(page.locator(".math-keyboard-host")).toBeVisible();
      expect(await page.locator("dialog.editor-dialog").count()).toBe(0);
      await page.screenshot({ path: evidence + "/page-math-keyboard.png" });
      await page
        .getByRole("button", { name: "Ocultar teclado matemático" })
        .click();
      await page.screenshot({ path: evidence + "/note-editor.png" });
      await coverage.reload();
      await expect(
        page.getByLabel("Nombre de la nota", { exact: true }),
      ).toHaveValue("Una nota desde el frontend independiente");
      await expect(editor).toContainText("Una idea matemática");
      await expect(page.locator("math-field").last()).toHaveJSProperty(
        "value",
        "\\frac{1}{2}",
      );
      await progress("draft-survived-reload");
      let lost = false;
      await page.route("**/api/study/v1/operations", async (route) => {
        if (!lost) {
          lost = true;
          await route.fetch();
          await route.abort("failed");
        } else await route.continue();
      });
      await page
        .getByRole("button", { name: "Guardar nota", exact: true })
        .click();
      await expect(
        page.getByRole("button", { name: "Reintentar el mismo envío" }),
      ).toBeVisible();
      await expect(editor).toContainText("Una idea matemática");
      await page
        .getByRole("button", { name: "Reintentar el mismo envío" })
        .click();
      await expect(
        page.getByRole("status").filter({ hasText: "Nota guardada." }).first(),
      ).toBeVisible();
      await expect(page).toHaveURL(/\/study\/notes\/note_/);
      await coverage.reload();
      await expect(
        page.getByRole("heading", { name: "Editar nota" }),
      ).toBeVisible();
      await expect(editor).toContainText("Una idea matemática");
      await page.screenshot({ path: evidence + "/saved-note-reloaded.png" });
      await progress("note-reloaded-after-lost-ack-retry");
      await page
        .getByRole("button", { name: "Incorporar como concepto" })
        .click();
      await expect(
        page.getByRole("heading", {
          name: "Una nota desde el frontend independiente",
          exact: true,
        }),
      ).toBeVisible();
      await page.getByRole("link", { name: "Ver en una esfera" }).click();
      await expect(page.locator(".knowledge-map canvas")).toBeVisible();
      await expect(page.locator(".selected-title")).toHaveText(
        "Una nota desde el frontend independiente",
      );
      await page.screenshot({ path: evidence + "/concept-in-sphere.png" });
      await page
        .getByRole("button", { name: "Leer concepto", exact: true })
        .click();
      await expect(
        page.getByRole("link", { name: /Volver al pasaje original/ }).first(),
      ).toBeVisible();
      await page
        .getByRole("link", { name: /Volver al pasaje original/ })
        .first()
        .click();
      await expect(
        page.locator('.page[data-page-number="1"] .textLayer span').first(),
      ).toBeVisible();
      await page.screenshot({ path: evidence + "/return-to-passage.png" });
      await page.goBack();
      await expect(
        page.getByRole("heading", {
          name: "Una nota desde el frontend independiente",
          exact: true,
        }),
      ).toBeVisible();
      expect(outside).toEqual([]);
      expect(errors).toEqual([]);
      await writeFile(
        evidence + "/browser.json",
        JSON.stringify(
          {
            browser: name,
            version: browser.version(),
            errors,
            outside,
            passed: true,
          },
          null,
          2,
        ),
      );
      passed = true;
    } catch (error) {
      await writeFile(
        evidence + "/failure.txt",
        String(error) +
          "\n" +
          JSON.stringify(errors),
      );
      // A diagnostic capture must not mask the original test failure.
      await page.screenshot({ path: evidence + "/failure.png", timeout: 5000 }).catch(async (captureError) => {
        await writeFile(evidence + "/capture-failure.txt", String(captureError));
      });
      throw error;
    } finally {
      await coverage.finish(passed);
      await context.close();
      await browser.close();
    }
  },
);
