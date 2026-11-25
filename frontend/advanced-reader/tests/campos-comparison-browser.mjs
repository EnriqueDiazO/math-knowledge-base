/** Exact historical Campos content: visible access, edit, reload, provenance and exports. */
import { chromium, firefox, expect } from "@playwright/test";
import { mkdir, readFile, writeFile } from "node:fs/promises";
import { resolve } from "node:path";
import { createHash } from "node:crypto";
const root = resolve("../../evidence/sonar/cpi-five-images-2026-11-24"),
  own = JSON.parse(
    await readFile(resolve(root, "owned-comparison.json"), "utf8"),
  ),
  name = process.env.MATHMONGO_STUDY_BROWSER || "firefox",
  out = resolve(root, "campos-" + name);
await mkdir(out, { recursive: true });
const browser =
    name === "chrome"
      ? await chromium.launch({
          headless: true,
          executablePath: "/usr/bin/google-chrome",
          args: ["--no-sandbox"],
        })
      : await firefox.launch({ headless: true }),
  context = await browser.newContext({
    viewport: { width: 1440, height: 1000 },
    recordVideo: { dir: out, size: { width: 1440, height: 1000 } },
    reducedMotion: "reduce",
  }),
  page = await context.newPage(),
  proof = { browser: name, events: [], errors: [] },
  started = Date.now();
page.on("pageerror", (error) => proof.errors.push(error.message));
page.setDefaultTimeout(25000);
async function mark(label) {
  proof.events.push({ seconds: (Date.now() - started) / 1000, label });
  await page.screenshot({
    path: resolve(out, "step-" + proof.events.length + ".png"),
    fullPage: true,
  });
  await page.waitForTimeout(500);
}
async function detail() {
  return page.evaluate(async (key) => {
    const context = await (await fetch("/api/study/v1/context")).json();
    return (
      await fetch(
        "/api/study/v1/concepts/detail?" + new URLSearchParams({ key }),
        { headers: { "X-MathMongo-Library": context.library_id } },
      )
    ).json();
  }, own.campos.key);
}
try {
  await page.goto(own.instances.react.url + "/study");
  await page
    .getByRole("navigation", { name: "Navegación principal", exact: true })
    .getByRole("link", { name: "Conceptos", exact: true })
    .click();
  await page.getByLabel("Buscar conceptos", { exact: true }).fill("Campos");
  await page.getByRole("link", { name: "Campos", exact: true }).click();
  await expect(
    page.getByRole("heading", { name: "Campos", exact: true }),
  ).toBeVisible();
  const before = await detail();
  proof.latex_before = createHash("sha256")
    .update(before.contenido_latex)
    .digest("hex");
  expect(proof.latex_before).toBe(own.campos.latex_sha256);
  await expect(
    page.getByRole("complementary", {
      name: "Procedencia y contexto",
      exact: true,
    }),
  ).toContainText("Rudin");
  await mark("Visible menu, exact historical source and provenance");
  const inspection = page.waitForResponse((response) =>
    response.url().endsWith("/api/study/v1/catalog/preparation"),
  );
  await page
    .getByRole("link", { name: "Editar concepto", exact: true })
    .click();
  const state = await (await inspection).json();
  const prepare = page.getByRole("button", {
    name: "Preparar biblioteca",
    exact: true,
  });
  if (state.state === "pending") {
    await prepare.click();
    await expect(
      page.getByText(
        "Biblioteca preparada. Aún no se ha guardado esta ficha.",
        { exact: true },
      ),
    ).toBeVisible();
  }
  await page.getByText("Referencia y organización", { exact: true }).click();
  await page
    .getByRole("textbox", { name: "Comentario", exact: true })
    .fill("Comprobación aislada Campos " + name);
  await page
    .getByRole("button", { name: "Guardar concepto", exact: true })
    .click();
  await expect(
    page.getByRole("heading", { name: "Campos", exact: true }),
  ).toBeVisible();
  await page.reload();
  await expect(
    page.getByRole("heading", { name: "Campos", exact: true }),
  ).toBeVisible();
  const after = await detail();
  expect(after.comentario).toBe("Comprobación aislada Campos " + name);
  expect(after.contenido_latex).toBe(before.contenido_latex);
  expect(after.key).toBe(before.key);
  expect(after.reference).toEqual(before.reference);
  proof.latex_after = createHash("sha256")
    .update(after.contenido_latex)
    .digest("hex");
  await mark(
    "Saved metadata, reloaded, identical LaTeX and bibliographic record",
  );
  for (const [label, extension] of [
    ["Exportar proyecto TEX", "zip"],
    ["Exportar PDF", "pdf"],
  ]) {
    const download = page.waitForEvent("download", { timeout: 120000 });
    await page.getByRole("button", { name: label, exact: true }).click();
    const file = await download;
    await file.saveAs(resolve(out, "Campos." + extension));
    await mark(label + " downloaded from the saved concept");
  }
  proof.passed = true;
} catch (error) {
  proof.passed = false;
  proof.error = String(error);
  await page.screenshot({ path: resolve(out, "failed.png"), fullPage: true });
  throw error;
} finally {
  await page.close();
  await page.video().saveAs(resolve(out, "Campos.webm"));
  await writeFile(resolve(out, "browser.json"), JSON.stringify(proof, null, 2));
  await context.close();
  await browser.close();
}
