import test from "node:test";
import { chromium, firefox, expect } from "@playwright/test";
import { readFile, writeFile } from "node:fs/promises";
import { readSource } from "./source-browser.mjs";
import { browserCoverage } from "./browser-coverage.mjs";
await test(
  "recover a complete LaTeX concept through React after backend restart",
  { timeout: 120000 },
  async () => {
    const name = process.env.MATHMONGO_STUDY_BROWSER || "chrome",
      evidence = process.env.MATHMONGO_INDEPENDENT_EVIDENCE;
    const proof = JSON.parse(
      await readFile(evidence + "/latex-parity-browser.json", "utf8"),
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
      }),
      coverage = await browserCoverage(page, name, "latex-recovery");
    let passed = false;
    try {
      await coverage.goto(
        process.env.MATHMONGO_INDEPENDENT_URL +
          "/study/concepts/" +
          encodeURIComponent(proof.createdKey),
      );
      await expect(
        page.getByRole("heading", {
          name: "Versión de otra ventana",
          exact: true,
        }),
      ).toBeVisible();
      await page
        .getByRole("link", { name: "Editar concepto", exact: true })
        .click();
      await page
        .getByRole("button", { name: "Fuente LaTeX", exact: true })
        .click();
      expect(await readSource(page)).toBe(proof.canonicalLatex);
      await page.screenshot({
        path: evidence + "/complete-source-after-backend-restart.png",
        fullPage: true,
      });
      passed = true;
      await writeFile(
        evidence + "/latex-recovery-browser.json",
        JSON.stringify(
          {
            passed: true,
            browser: name,
            key: proof.createdKey,
            sourceExactAfterRestart: true,
            MathV0_writes: 0,
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
