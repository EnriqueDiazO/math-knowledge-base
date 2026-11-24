import { readSource } from "./source-browser.mjs";
import test from "node:test";
import { chromium, firefox, expect } from "@playwright/test";
import { readFile, writeFile } from "node:fs/promises";
import { createHash } from "node:crypto";
import { browserCoverage } from "./browser-coverage.mjs";

await test(
  "real copied legacy documents remain byte-identical through visual read and no-op edit",
  { timeout: 150000 },
  async () => {
    const name = process.env.MATHMONGO_STUDY_BROWSER ?? "chrome",
      base = process.env.MATHMONGO_INDEPENDENT_URL,
      evidence = process.env.MATHMONGO_INDEPENDENT_EVIDENCE;
    const cases = JSON.parse(
      await readFile(process.env.MATHMONGO_LEGACY_CASES, "utf8"),
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
    const coverage = await browserCoverage(page, name, "legacy");
    let passed = false;
    const errors = [],
      checks = [];
    page.on("pageerror", (error) => errors.push(error.message));
    page.setDefaultTimeout(20000);
    const read = (key) =>
      page.evaluate(async (key) => {
        const scope = await (await fetch("/api/study/v1/context")).json();
        const response = await fetch(
          "/api/study/v1/concepts/detail?" + new URLSearchParams({ key }),
          { headers: { "X-MathMongo-Library": scope.library_id } },
        );
        if (!response.ok) throw new Error("Read failed");
        return response.json();
      }, key);
    try {
      for (const item of cases) {
        await coverage.goto(
          base + "/study/concepts/" + encodeURIComponent(item.key),
        );
        await expect(
          page.getByRole("heading", { name: item.title, exact: true }),
        ).toBeVisible();
        const before = await read(item.key);
        if (item.case === "john") {
          await expect(page.locator(".reading-document")).toContainText(
            "Acuñó el término",
          );
          await expect(
            page.locator(
              '.reading-document a[href="https://doi.org/10.1145/367177.367199"]',
            ),
          ).toHaveText("McCarthy, 1960");
        }
        if (item.case === "mathematics")
          expect(
            await page.locator(".reading-document math-field").count(),
          ).toBeGreaterThan(1);
        if (["custom", "tikz"].includes(item.case))
          expect(
            await page.locator("[data-source-block]").count(),
          ).toBeGreaterThan(0);
        await page.screenshot({
          path: evidence + "/legacy-" + item.case + ".png",
          fullPage: true,
        });
        await page.getByRole("link", { name: "Editar concepto", exact: true }).click();
        await expect(
          page.getByRole("heading", { name: "Editar concepto", exact: true }),
        ).toBeVisible();
        await page
          .getByRole("button", { name: "Fuente LaTeX", exact: true })
          .click();
        expect(await readSource(page)).toBe(before.contenido_latex);
        await page
          .getByRole("button", { name: "Guardar concepto", exact: true })
          .click();
        await expect(
          page.getByRole("heading", { name: item.title, exact: true }),
        ).toBeVisible();
        const after = await read(item.key),
          hash = createHash("sha256")
            .update(after.contenido_latex)
            .digest("hex");
        expect(after.contenido_latex).toBe(before.contenido_latex);
        expect(hash).toBe(item.sha256);
        expect(after.key).toBe(item.key);
        checks.push({
          case: item.case,
          key: item.key,
          sha256: hash,
          preserved: true,
        });
      }
      expect(errors).toEqual([]);
      passed = true;
      await writeFile(
        evidence + "/legacy-browser.json",
        JSON.stringify(
          { passed, browser: name, version: browser.version(), checks, errors },
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
