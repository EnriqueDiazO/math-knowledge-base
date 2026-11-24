import test from "node:test";
import { chromium, firefox, expect } from "@playwright/test";
import { readFile, writeFile } from "node:fs/promises";
import { spawnSync } from "node:child_process";
import { createHash } from "node:crypto";
import { browserCoverage } from "./browser-coverage.mjs";
import { writeSource } from "./source-browser.mjs";
await test(
  "whole academic notes: historical copy, shared resources, conflict and lost deletion recovery",
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
      coverage = await browserCoverage(page, name, "note-actions");
    const cases = JSON.parse(
        await readFile(process.env.MATHMONGO_NOTE_ACTIONS_CASES, "utf8"),
      ),
      proof = [];
    let passed = false;
    const button = (label) =>
      page.getByRole("button", { name: label, exact: true });
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
          return { status: result.status, body: await result.json() };
        },
        { path, body },
      );
    const manage = async () => {
      const details = page.locator(".study-note-management");
      if (
        !(await details.getAttribute("open")) &&
        !(await details.evaluate((el) => el.open))
      )
        await details.getByText("Gestionar esta nota", { exact: true }).click();
    };
    try {
      for (const item of cases) {
        const family = item.family,
          root = family === "diary" ? "/notebook" : "/structured/" + family,
          route =
            family === "diary"
              ? "/study/notebook"
              : "/study/notebook/" + family,
          path = root + "/" + item.id;
        await coverage.goto(base + route + "/" + encodeURIComponent(item.id));
        const initial = (await request(path)).body;
        expect(
          createHash("sha256").update(initial.latex_body).digest("hex"),
        ).toBe(item.latex_sha256);
        if (family !== "diary") {
          await manage();
          await button("Duplicar nota completa").click();
          await page
            .getByLabel("Título de la copia", { exact: true })
            .fill("Copia completa " + family);
          const requests = [];
          let lost = false;
          await page.route(
            "**/api/study/v1" + path + "/actions",
            async (route) => {
              requests.push(route.request().postDataJSON());
              if (!lost) {
                lost = true;
                expect((await route.fetch()).ok()).toBe(true);
                await route.abort("failed");
              } else await route.continue();
            },
          );
          await button("Crear copia de esta nota").click();
          await expect(button("Reintentar la misma operación")).toBeVisible();
          await coverage.reload();
          await button("Reintentar la misma operación").click();
          await expect(page).toHaveURL(new RegExp(family + "_copy_", "u"));
          await page.unroute("**/api/study/v1" + path + "/actions");
          expect(requests).toHaveLength(2);
          expect(requests[1]).toEqual(requests[0]);
          const copyId = new URL(page.url()).pathname.split("/").at(-1),
            copy = (await request(root + "/" + copyId)).body;
          expect(copy.latex_body).toBe(initial.latex_body);
          expect(copy.document).toEqual(initial.document);
          if (item.resource_sha256) {
            const exported = page.waitForEvent("download");
            await button("Exportar proyecto TEX").click();
            const bundlePath = evidence + "/note-copy-cpi-resources.zip";
            await (await exported).saveAs(bundlePath);
            const result = spawnSync(
              "python3",
              [
                "-c",
                "import hashlib,sys,zipfile; z=zipfile.ZipFile(sys.argv[1]); n=next(n for n in z.namelist() if n.endswith('/images/note-actions.png')); print(hashlib.sha256(z.read(n)).hexdigest())",
                bundlePath,
              ],
              { encoding: "utf8" },
            );
            expect(result.status).toBe(0);
            expect(result.stdout.trim()).toBe(item.resource_sha256);
            const pdf = page.waitForEvent("download");
            await button("Exportar PDF").click();
            const pdfPath = evidence + "/note-copy-cpi-resources.pdf";
            await (await pdf).saveAs(pdfPath);
            expect((await readFile(pdfPath)).subarray(0, 5).toString()).toBe(
              "%PDF-",
            );
          }
          await page.screenshot({
            path: evidence + "/note-copy-" + family + ".png",
            fullPage: true,
          });
          // Remove only the new copy; the immutable historical input remains unchanged.
          await manage();
          await button("Eliminar nota guardada…").click();
          const copyTitle = copy.metadata.title;
          await page
            .getByLabel("Escribe el nombre de la nota para confirmar", {
              exact: true,
            })
            .fill("otra nota");
          await expect(
            button("Confirmar eliminación de esta nota"),
          ).toBeDisabled();
          await page
            .getByLabel("Escribe el nombre de la nota para confirmar", {
              exact: true,
            })
            .fill(copyTitle);
          await button("Confirmar eliminación de esta nota").click();
          await expect(page).toHaveURL(base + route);
          expect((await request(path)).body).toEqual(initial);
          await page.getByText("Filtrar notas", { exact: true }).click();
          await page
            .getByLabel("Proyecto exacto", { exact: true })
            .fill(initial.metadata.project || "");
          await page
            .getByLabel("Contexto exacto", { exact: true })
            .fill(initial.metadata.context || "");
          const date = String(initial.metadata.date || "").slice(0, 10);
          if (/^\d{4}-\d{2}-\d{2}$/u.test(date)) {
            await page.getByLabel("Desde la fecha", { exact: true }).fill(date);
            await page.getByLabel("Hasta la fecha", { exact: true }).fill(date);
          }
          await button("Buscar notas").click();
          await expect(
            page.getByRole("link", {
              name: initial.metadata.title || "Sin título",
              exact: true,
            }),
          ).toBeVisible();
          await coverage.reload();
          await expect(
            page.getByLabel("Proyecto exacto", { exact: true }),
          ).toHaveValue(initial.metadata.project || "");
          proof.push({
            family,
            originalId: item.id,
            copiedId: copyId,
            exactLatex: true,
            exactDocument: true,
            copyRetryExact: true,
            copyDeletedOriginalUnchanged: true,
            filtersPersisted: true,
          });
        } else {
          await button("Fuente LaTeX").click();
          await writeSource(
            page,
            initial.latex_body + "\nBorrador privado sin publicar.",
          );
          await manage();
          await button("Eliminar nota guardada…").click();
          await page
            .getByLabel("Escribe el nombre de la nota para confirmar", {
              exact: true,
            })
            .fill(initial.title);
          let lost = false;
          const writes = [];
          await page.route(
            "**/api/study/v1" + path + "/actions",
            async (route) => {
              writes.push(route.request().postDataJSON());
              if (!lost) {
                lost = true;
                expect((await route.fetch()).ok()).toBe(true);
                await route.abort("failed");
              } else await route.continue();
            },
          );
          await button("Confirmar eliminación de esta nota").click();
          await expect(button("Reintentar la misma operación")).toBeVisible();
          expect((await request(path)).status).toBe(404);
          await coverage.reload();
          await expect(button("Reintentar la misma operación")).toBeVisible();
          // Read the raw browser draft independently of whether its note still exists.
          const savedDraft = await page.evaluate(
            (id) =>
              Object.entries(localStorage).find(
                ([key]) =>
                  key.startsWith("mathmongo-diary-v1-") &&
                  key.endsWith("-" + id),
              )?.[1],
            item.id,
          );
          expect(savedDraft).toContain("Borrador privado sin publicar.");
          await page.screenshot({
            path: evidence + "/note-delete-recovery.png",
            fullPage: true,
          });
          await button("Reintentar la misma operación").click();
          await expect(page).toHaveURL(base + route);
          expect(writes[1]).toEqual(writes[0]);
          await page.unroute("**/api/study/v1" + path + "/actions");
          proof.push({
            family,
            originalId: item.id,
            deleted: true,
            requestRecoveredAfter404: true,
            exactDeleteRetry: true,
            localDraftKept: true,
          });
        }
      }
      expect(proof).toHaveLength(3);
      await writeFile(
        evidence + "/note-actions-browser.json",
        JSON.stringify(
          {
            browser: name,
            passed: true,
            cases: proof,
            streamlit_started: false,
            MathV0_writes: 0,
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
