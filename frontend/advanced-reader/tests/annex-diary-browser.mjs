/** Reproduce the exact saved Diario export, then verify the same entry through the corrected UI. */
import test from "node:test";
import { chromium, firefox, expect } from "@playwright/test";
import { readFile, mkdir, writeFile } from "node:fs/promises";
import { resolve } from "node:path";
import { createHash } from "node:crypto";
await test(
  "reported Diario export uses saved source and produces a portable PDF",
  { timeout: 240000 },
  async () => {
    const root = resolve("../../evidence/sonar/cpi-five-images-2026-11-24"),
      own = JSON.parse(
        await readFile(resolve(root, "owned-comparison.json"), "utf8"),
      ),
      phase = process.env.MATHMONGO_ANNEX_PHASE || "after",
      name = process.env.MATHMONGO_STUDY_BROWSER || "chrome",
      base =
        phase === "before" ? "http://127.0.0.1:8766" : own.instances.react.url,
      out = resolve(root, "diary-ui-" + phase + "-" + name),
      id = "6a81d4fb010f2a0daff07fb5";
    await mkdir(out, { recursive: true, mode: 0o700 });
    const browser =
        name === "firefox"
          ? await firefox.launch({ headless: true })
          : await chromium.launch({
              headless: true,
              executablePath: "/usr/bin/google-chrome",
              args: ["--no-sandbox"],
            }),
      context = await browser.newContext({
        viewport: { width: 1440, height: 1000 },
        recordVideo: { dir: out, size: { width: 1440, height: 1000 } },
        reducedMotion: "reduce",
      }),
      page = await context.newPage(),
      proof = { phase, browser: name, events: [], errors: [] },
      start = Date.now();
    page.on("pageerror", (error) => proof.errors.push(error.message));
    page.setDefaultTimeout(30000);
    const mark = async (label) => {
      proof.events.push({ seconds: (Date.now() - start) / 1000, label });
      await page.screenshot({
        path: resolve(out, "step-" + proof.events.length + ".png"),
        timeout: 20000,
      });
      await page.waitForTimeout(600);
    };
    const saved = () =>
      page.evaluate(async (id) => {
        const ctx = await (await fetch("/api/study/v1/context")).json();
        const note = await (
          await fetch("/api/study/v1/notebook/" + id, {
            headers: { "X-MathMongo-Library": ctx.library_id },
          })
        ).json();
        return { context: ctx, note };
      }, id);
    try {
      await page.goto(base + "/study/notebook/" + id);
      await expect(
        page.getByRole("heading", {
          name: "Editar entrada del Cuaderno",
          exact: true,
        }),
      ).toBeVisible();
      const initial = await saved();
      proof.library = initial.context.name;
      proof.revision = initial.note.revision;
      proof.latex_sha256 = createHash("sha256")
        .update(initial.note.latex_body)
        .digest("hex");
      expect(proof.latex_sha256).toBe(
        "379bdeef015811e5222b5abbf1fcedc1f721ba639293d60b7270277351b2283d",
      );
      expect(initial.note.image_count).toBe(33);
      await mark(
        "Saved real entry, source revision and 33 preserved associations",
      );
      const button = page.getByRole("button", {
        name: "Exportar PDF",
        exact: true,
      });
      if (phase === "before") {
        const response = page.waitForResponse(
          (r) =>
            r.url().endsWith("/notebook/" + id + "/export") &&
            r.request().method() === "POST",
        );
        await button.click();
        const failed = await response;
        proof.http_status = failed.status();
        proof.failure = await failed.json();
        expect(failed.status()).toBe(422);
        proof.details_accessible = await page
          .getByText("Detalles de compilación", { exact: true })
          .count();
        await mark(
          "Original runtime fails export and offers no accessible compilation details",
        );
      } else {
        for (let i = 1; i <= 2; i++) {
          const download = page.waitForEvent("download", { timeout: 120000 });
          await button.click();
          const file = await download;
          await file.saveAs(resolve(out, "Diario-" + i + ".pdf"));
          expect(
            (await readFile(resolve(out, "Diario-" + i + ".pdf")))
              .subarray(0, 5)
              .toString(),
          ).toBe("%PDF-");
          await mark("Real PDF download " + i);
          if (i === 1) {
            await page.reload();
            await expect(
              page.getByRole("heading", {
                name: "Editar entrada del Cuaderno",
                exact: true,
              }),
            ).toBeVisible();
            const reopened = await saved();
            expect(reopened.note.revision).toBe(initial.note.revision);
            expect(reopened.note.latex_body).toBe(initial.note.latex_body);
            await mark(
              "Reloaded unchanged saved revision; associations preserved",
            );
          }
        }
        const download = page.waitForEvent("download");
        await page
          .getByRole("button", { name: "Exportar proyecto TEX", exact: true })
          .click();
        await (await download).saveAs(resolve(out, "Diario.zip"));
        await mark("Portable TEX downloaded from the same saved entry");
      }
      expect((await saved()).note.revision).toBe(initial.note.revision);
      proof.passed = true;
    } catch (error) {
      proof.passed = false;
      proof.error = String(error);
      await page
        .screenshot({ path: resolve(out, "failed.png"), timeout: 20000 })
        .catch(() => {});
      throw error;
    } finally {
      await page.close();
      await page.video().saveAs(resolve(out, "Diario.webm"));
      await writeFile(
        resolve(out, "browser.json"),
        JSON.stringify(proof, null, 2),
      );
      await context.close();
      await browser.close();
    }
  },
);
