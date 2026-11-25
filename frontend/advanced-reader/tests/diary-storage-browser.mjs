/** Exercise real Web Storage quota and IndexedDB against the packaged UI, without touching MongoDB. */
import test from "node:test";
import { fileURLToPath } from "node:url";
import { chromium, expect, firefox } from "@playwright/test";
import { readSource, writeSource } from "./source-browser.mjs";

const base = "http://127.0.0.1:8766";
const identity = "diary-quota-fixture";
const path = "/study/notebook/" + identity;
const key = "mathmongo-diary-v1-quota-fixture-" + identity;
const context = {
  library_id: "quota-fixture", runtime_id: "fixture", name: "Prueba de cuota",
  preparation: { state: "ready", notes_ready: true, reading_ready: true },
};
const fields = {
  title: "Entrada guardada", latex_body: "Texto original con $x^2$.", date: "2026-11-01",
  project: "Álgebra", context: "estudio", tags: ["literal, etiqueta"],
};
const legacy = JSON.stringify({
  ...fields,
  title: "Borrador anterior", tags: fields.tags.join("\n"), references: "[]",
  original: JSON.stringify({ ...fields, catalog_reference_ids: [] }),
  revision: "a".repeat(64), snapshot: "", pending: "", request_id: "legacy",
});
const nextTitle = "Borrador reciente con cuota agotada y respaldo en el navegador";
const nextBody = String.raw`Texto conservado con $\frac{1}{2}$ y acento en Álgebra.`;

await test("Diario recovers from a full localStorage and retries the same durable save", { timeout: 45000 }, async () => {
  const browser = process.env.MATHMONGO_STUDY_BROWSER === "chrome"
    ? await chromium.launch({ executablePath: "/usr/bin/google-chrome", headless: true })
    : await firefox.launch({ headless: true });
  try {
    const page = await browser.newPage({ reducedMotion: "reduce" });
    page.setDefaultTimeout(8000);
    const errors = [], writes = [];
    let note = {
      ...fields, note_id: identity, revision: "a".repeat(64),
      references: [], image_count: 0,
    };
    const frontend = new URL("../../../mathmongo/advanced_reader/static/advanced_reader/", import.meta.url);
    page.on("pageerror", (error) => errors.push(error.message));
    await page.route(base + "/**", async (route) => {
      const pathname = new URL(route.request().url()).pathname;
      if (pathname === "/__quota_fixture__")
        return route.fulfill({ contentType: "text/html", body: "<!DOCTYPE html>" });
      if (pathname === "/api/study/v1/context") return route.fulfill({ json: context });
      if (pathname === "/api/study/v1/notebook/" + identity) {
        if (route.request().method() === "POST") {
          writes.push(route.request().postDataJSON());
          note = { ...note, ...writes.at(-1).changes, revision: "b".repeat(64) };
          if (writes.length === 1) return route.abort("failed");
        }
        return route.fulfill({ json: note });
      }
      if (pathname.startsWith("/assets/"))
        return route.fulfill({ path: fileURLToPath(new URL(pathname.slice(1), frontend)) });
      if (pathname.startsWith("/study"))
        return route.fulfill({ path: fileURLToPath(new URL("index.html", frontend)) });
      return route.fulfill({ status: 404 });
    });
    await page.goto(base + "/__quota_fixture__");
    const pressure = await page.evaluate(({ key, legacy }) => {
      localStorage.setItem(key, legacy);
      for (let size = 1024 * 1024; size > 0; size /= 2) {
        for (let index = 0; index < 12; index++) {
          try {
            localStorage.setItem("quota-fixture-" + size + "-" + index, "x".repeat(size));
          } catch (error) {
            if (error.name !== "QuotaExceededError") throw error;
            break;
          }
        }
        if (size === 1) break;
      }
      try {
        localStorage.setItem("quota-fixture-probe", "x".repeat(256));
        return "unexpected write";
      } catch (error) {
        return error.name;
      }
    }, { key, legacy });
    expect(pressure).toBe("QuotaExceededError");

    const title = page.getByLabel("Título de la entrada", { exact: true });
    const button = (name) => page.getByRole("button", { name, exact: true });
    await page.goto(base + path);
    await expect(title).toHaveValue("Borrador anterior");
    await title.fill(nextTitle);
    await expect(button("Fuente LaTeX")).toBeVisible({ timeout: 4000 });
    await button("Fuente LaTeX").click();
    await writeSource(page, nextBody);
    await expect.poll(() => readSource(page)).toBe(nextBody);
    expect(writes).toHaveLength(0);
    expect(await page.evaluate((key) => localStorage.getItem(key), key)).toBe(legacy);

    // Saving protects the exact pending request before sending it. The reply is lost once.
    await button("Guardar entrada").click();
    await expect(page.getByText(/No se confirmó la conexión/)).toBeVisible();
    await page.goto(base + "/study");
    const recovered = page.getByRole("link", { name: nextTitle, exact: true });
    await expect(recovered).toHaveAttribute("href", path);
    await recovered.click();
    await expect(title).toHaveValue(nextTitle);
    await button("Reintentar el mismo guardado").click();
    await expect(page.getByText("Entrada guardada y confirmada en esta biblioteca.")).toBeVisible();
    expect(writes).toHaveLength(2);
    expect(writes[1]).toEqual(writes[0]);
    expect(note.latex_body).toBe(nextBody);
    expect(note.tags).toEqual(fields.tags);
    expect(errors).toEqual([]);
  } finally {
    await browser.close();
  }
});
