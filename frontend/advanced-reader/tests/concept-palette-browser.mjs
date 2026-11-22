/** Actual autonomous build and owned library; no UI snapshots or service mocks. */
import { chromium, firefox, expect } from "@playwright/test";
import { readFile, writeFile } from "node:fs/promises";
import test from "node:test";

await test(
  "mathematical identity, keyboard and recoverable wide-page draft",
  { timeout: 150000 },
  async () => {
    const types = JSON.parse(
      await readFile(
        new URL("../../../editor/ui/concept_types.json", import.meta.url),
        "utf8",
      ),
    );
    const name = process.env.MATHMONGO_STUDY_BROWSER ?? "chrome";
    const browser =
      name === "firefox"
        ? await firefox.launch({ headless: true })
        : await chromium.launch({
            executablePath: "/usr/bin/google-chrome",
            headless: true,
            args: ["--no-sandbox"],
          });
    const context = await browser.newContext({
      viewport: { width: 1440, height: 1080 },
      reducedMotion: "reduce",
      deviceScaleFactor: 1,
    });
    const page = await context.newPage();
    page.setDefaultTimeout(20000);
    const base = process.env.MATHMONGO_INDEPENDENT_URL,
      evidence = process.env.MATHMONGO_INDEPENDENT_EVIDENCE;
    const errors = [],
      external = [];
    page.on("pageerror", (error) => errors.push(error.message));
    page.on("request", (request) => {
      if (
        !request.url().startsWith(base) &&
        !/^(data|blob):/u.test(request.url())
      )
        external.push(request.url());
    });
    const color = (hex) =>
      `rgb(${hex
        .slice(1)
        .match(/../gu)
        .map((value) => parseInt(value, 16))
        .join(", ")})`;
    const sample = Object.entries(types)
      .map(
        ([key, type]) =>
          `\\begin{cth${key}}{${type.label} de prueba}\nUna fórmula real $\\frac{1}{2}$ y $\\int_0^1 x^2\\,dx$.\n\\end{cth${key}}`,
      )
      .join("\n\n");
    const measured = {};
    const stages = {};
    const captureDraft = () =>
      page.evaluate(() =>
        Object.fromEntries(
          Object.entries(localStorage)
            .filter(([key]) => key.startsWith("mathmongo-drafts-v2-"))
            .map(([key, value]) => [key, JSON.parse(value)]),
        ),
      );
    try {
      await page.goto(base + "/study/settings/appearance");
      await expect(
        page.getByRole("heading", { name: "Tipos matemáticos" }),
      ).toBeVisible();
      for (const [key, type] of Object.entries(types)) {
        const block = page.locator(
          `.reading-document section[data-concept-type="${key}"]`,
        );
        await expect(block).toHaveAttribute("aria-label", type.label);
        await expect(block.locator("header")).toHaveCSS(
          "color",
          color(type.accent),
        );
        measured[key] = await block.locator("header").evaluate((element) => ({
          title: getComputedStyle(element).color,
          background: getComputedStyle(element).backgroundColor,
        }));
        await expect(block.locator("math-field")).toHaveCount(2);
        if (key === "proposicion") await expect(block).toHaveCSS("border-left-style", "double");
      }
      await page.screenshot({
        path: evidence + "/all-types-reading.png",
        fullPage: true,
      });
      await page.goto(
        base +
          "/study/write?source=" +
          encodeURIComponent(process.env.MATHMONGO_PALETTE_SOURCE),
      );
      await expect(
        page.getByRole("heading", { name: "Escribir nota" }),
      ).toBeVisible();
      await page
        .getByRole("textbox", { name: "Nombre de la nota" })
        .fill("Muestra de tipos matemáticos");
      await page
        .getByRole("button", { name: "Fuente LaTeX", exact: true })
        .click();
      await page
        .getByRole("textbox", { name: "Fuente LaTeX", exact: true })
        .fill(sample);
      await page
        .getByRole("button", { name: "Fuente LaTeX", exact: true })
        .click();
      await expect(
        page.locator(".visual-document section[data-concept-type]"),
      ).toHaveCount(8);
      stages.visual = await captureDraft();
      await page.getByRole("button", { name: "Negrita", exact: true }).focus();
      expect(
        await page
          .getByRole("button", { name: "Negrita", exact: true })
          .evaluate((element) => getComputedStyle(element).outlineStyle),
      ).toBe("solid");
      await page.keyboard.press("Tab");
      await expect(
        page.getByRole("button", { name: "Énfasis", exact: true }),
      ).toBeFocused();
      await page.screenshot({ path: evidence + "/editor-types-wide.png" });
      const field = page.locator(".visual-document math-field").first();
      await field.locator('[part="virtual-keyboard-toggle"]').click();
      await expect(page.locator(".math-keyboard-host")).toBeVisible();
      expect(
        await page
          .locator(".math-keyboard-host")
          .evaluate((element) =>
            getComputedStyle(element)
              .getPropertyValue("--keyboard-background")
              .trim(),
          ),
      ).toBe("#091A27");
      await page.screenshot({ path: evidence + "/editor-types-keyboard.png" });
      await page
        .getByRole("button", { name: "Ocultar teclado matemático" })
        .click();
      stages.keyboard = await captureDraft();
      const draftUrl = page.url();
      await page.reload();
      await expect(
        page.locator(".visual-document section[data-concept-type]"),
      ).toHaveCount(8);
      stages.reloaded = await captureDraft();
      await writeFile(
        evidence + "/palette-draft-stages.json",
        JSON.stringify(stages, null, 2),
      );
      await page
        .getByRole("button", { name: "Fuente LaTeX", exact: true })
        .click();
      await expect(
        page.getByRole("textbox", { name: "Fuente LaTeX", exact: true }),
      ).toHaveValue(sample);
      await page
        .getByRole("button", { name: "Fuente LaTeX", exact: true })
        .click();
      await page.setViewportSize({ width: 390, height: 844 });
      const narrowLayout = await page.evaluate(() => {
        const tools = document.querySelector(".document-toolbar").getBoundingClientRect();
        const documentSurface = document.querySelector(".study-document-viewport").getBoundingClientRect();
        const actions = document.querySelector(".study-document-actions").getBoundingClientRect();
        return { toolbarHeight: tools.height, surfaceBottom: documentSurface.bottom, actionsTop: actions.top };
      });
      expect(narrowLayout.toolbarHeight).toBeLessThan(110);
      expect(narrowLayout.actionsTop).toBeGreaterThanOrEqual(narrowLayout.surfaceBottom);
      await page.screenshot({
        path: evidence + "/editor-types-narrow.png",
        fullPage: true,
      });
      expect(
        await page.evaluate(
          () => document.documentElement.scrollWidth <= innerWidth,
        ),
      ).toBe(true);
      await page.goto(base + "/study/settings/appearance");
      await expect(
        page.locator(".reading-document section[data-concept-type]"),
      ).toHaveCount(8);
      expect(
        await page.evaluate(
          () => document.documentElement.scrollWidth <= innerWidth,
        ),
      ).toBe(true);
      await page.screenshot({
        path: evidence + "/all-types-narrow.png",
        fullPage: true,
      });
      await page.setViewportSize({ width: 1440, height: 1080 });
      await page.goto(base + "/study/spaces");
      await expect(page.locator(".knowledge-map canvas")).toBeVisible();
      await page.getByText("Leyenda y ayuda", { exact: true }).click();
      for (const type of Object.values(types))
        await expect(
          page
            .locator(".legend")
            .getByText(`${type.symbol} · ${type.label}`, { exact: true }),
        ).toBeVisible();
      await page.screenshot({
        path: evidence + "/sphere-all-types.png",
        fullPage: true,
      });
      expect(errors).toEqual([]);
      expect(external).toEqual([]);
      await writeFile(
        evidence + "/palette-browser.json",
        JSON.stringify(
          {
            browser: name,
            version: browser.version(),
            zoom: 1,
            deviceScaleFactor: 1,
            viewports: [
              [1440, 1080],
              [390, 844],
            ],
            reducedMotion: "reduce",
            keyboardFocus: true,
            narrowLayout,
            formulas: true,
            unpublishedDraftRecovered: true,
            draftUrl: new URL(draftUrl).pathname,
            colors: measured,
            errors,
            external,
          },
          null,
          2,
        ),
      );
    } finally {
      await context.close();
      await browser.close();
    }
  },
);
