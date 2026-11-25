/** Inspect historical destinations and their real controls, without submitting maintenance or import actions. */
import { expect } from "@playwright/test";
import { readFile, mkdir, writeFile } from "node:fs/promises";
import { resolve } from "node:path";
import { firefoxAtZoom } from "./firefox-native-zoom.mjs";
const root = resolve("../../evidence/sonar/cpi-five-images-2026-11-24"),
  own = JSON.parse(
    await readFile(resolve(root, "owned-comparison.json"), "utf8"),
  ),
  out = resolve(root, "historical-destinations");
await mkdir(out, { recursive: true });
const browser = await firefoxAtZoom(own.instances.streamlit.url, 100, out),
  proof = { destinations: [], errors: [] };
const destinations = [
  ["Inicio", "inicio"],
  ["Add Source", "fuente-nueva"],
  ["Edit Source", "fuentes"],
  ["Reading Space", "lectura"],
  ["Documentos", "documentos"],
  ["Nuevo concepto", "concepto-nuevo"],
  ["Editar concepto", "concepto-editar"],
  ["Conceptos", "conceptos"],
  ["Relaciones", "relaciones"],
  ["Grafo de conocimiento", "grafo"],
  ["Habitación de estudio", "habitacion"],
  ["Exportar", "exportar"],
  ["Exportar base", "exportar-base"],
  ["Importar base", "importar-base"],
  ["Mantenimiento", "mantenimiento"],
  ["Configuración", "configuracion"],
  ["Diagnóstico", "diagnostico"],
];
try {
  for (const [label, file] of destinations) {
    const page = await browser.context.newPage(),
      start = Date.now();
    page.setDefaultTimeout(30000);
    try {
      await page.goto(own.instances.streamlit.url);
      const nav = page.getByRole("combobox", {
        name: "Navegación",
        exact: true,
      });
      await expect(nav).toBeVisible({ timeout: 60000 });
      await nav.focus();
      await nav.fill(label);
      await nav.press("ArrowDown");
      const names = await page.getByRole("option").allTextContents();
      const option = page
        .getByRole("option")
        .filter({
          hasText: new RegExp(
            label.replace(/[.*+?^${}()|[\]\\]/g, "\\$&") + "$",
          ),
        })
        .first();
      if (await option.count()) await option.click();
      else await nav.press("Enter");
      await page.waitForTimeout(1200);
      await expect(page.getByTestId("stException")).toHaveCount(0);
      await page.screenshot({
        path: resolve(out, file + ".png"),
        fullPage: true,
      });
      const snapshot = await page.locator("body").ariaSnapshot();
      await writeFile(resolve(out, file + ".yml"), snapshot);
      proof.destinations.push({
        name: label,
        seconds: (Date.now() - start) / 1000,
        matched_options: names,
        controls_inspected: true,
        write_operation_verified: false,
      });
    } catch (error) {
      proof.errors.push({ name: label, error: String(error) });
      await page.screenshot({
        path: resolve(out, file + "-failed.png"),
        fullPage: true,
      });
    } finally {
      await page.close();
      await page.video().saveAs(resolve(out, file + ".webm"));
    }
  }
  proof.passed = proof.errors.length === 0;
} finally {
  await writeFile(
    resolve(out, "destinations.json"),
    JSON.stringify(proof, null, 2),
  );
  await browser.close();
}
