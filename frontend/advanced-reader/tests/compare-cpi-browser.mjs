/** Actual interfaces, isolated historical resources and downloaded academic artifacts. */
import { firefox, chromium, expect } from "@playwright/test";
import { readFile, writeFile, mkdir } from "node:fs/promises";
import { resolve } from "node:path";
const root = resolve("../.."),
  directory = resolve(root, "evidence/sonar/cpi-five-images-2026-11-24");
const settings = JSON.parse(
  await readFile(resolve(directory, "owned-comparison.json"), "utf8"),
);
const phase = process.env.MATHMONGO_COMPARE_PHASE || "before",
  browserName = process.env.MATHMONGO_STUDY_BROWSER || "firefox";
const output = resolve(directory, phase + "-" + browserName);
await mkdir(output, { recursive: true });
const browser =
  browserName === "firefox"
    ? await firefox.launch({ headless: true })
    : await chromium.launch({
        headless: true,
        executablePath: "/usr/bin/google-chrome",
        args: ["--no-sandbox"],
      });
const page = await browser.newPage({
    viewport: { width: 1440, height: 1000 },
    reducedMotion: "reduce",
  }),
  errors = [],
  network = [],
  proof = {
    phase,
    browser: browserName,
    errors,
    network,
    screens: [],
    zoom: [],
  };
page.on("pageerror", (e) => errors.push(e.message));
page.on("response", (r) => {
  if (r.status() >= 400) network.push({ url: r.url(), status: r.status() });
});
const button = (name) => page.getByRole("button", { name, exact: true });
async function shot(label) {
  await page.screenshot({
    path: resolve(output, label + ".png"),
    fullPage: true,
  });
  proof.screens.push(label);
}
async function scaled(label) {
  await shot(label + "-100");
  const before = await page.evaluate(() => ({
    dpr: devicePixelRatio,
    width: innerWidth,
  }));
  await page.keyboard.press("Control+-");
  await page.keyboard.press("Control+-");
  await page.keyboard.press("Control+-");
  const after = await page.evaluate(() => ({
    dpr: devicePixelRatio,
    width: innerWidth,
  }));
  const native = before.dpr !== after.dpr;
  if (!native)
    await page.evaluate(() => {
      document.documentElement.style.zoom = "0.7";
    });
  proof.zoom.push({
    label,
    before,
    after,
    native,
    mode: native
      ? "browser-shortcut"
      : "CSS 70% emulation; native browser UI unavailable through Playwright",
  });
  await shot(label + "-70");
  if (native) await page.keyboard.press("Control+0");
  else
    await page.evaluate(() => {
      document.documentElement.style.zoom = "";
    });
}
try {
  if (phase === "before") {
    await page.goto("http://127.0.0.1:8766/study");
    await expect(
      page.getByRole("heading", { name: "Leer, escribir, conectar" }),
    ).toBeVisible();
    await scaled("existing-react-home");
    await page.goto("http://127.0.0.1:8501");
    await expect(
      page.getByRole("combobox", { name: "Navegación", exact: true }),
    ).toBeVisible({ timeout: 60000 });
    await scaled("existing-streamlit-home");
  }
  await page.goto(settings.instances.streamlit.url);
  const navigation = page.getByRole("combobox", {
    name: "Navegación",
    exact: true,
  });
  await navigation.click({ timeout: 60000 });
  await navigation.fill("CPI");
  await page.getByRole("option", { name: "🟥 CPI", exact: true }).click();
  await page.getByText("Editar notas", { exact: true }).click();
  await button("Editar").first().click();
  await expect(
    page.getByRole("heading", { name: "Editar nota CPI", exact: true }),
  ).toBeVisible();
  await scaled("streamlit-cpi");
  if (phase === "before") {
    await button("Vista previa PDF").click();
    await expect(
      page.getByText("PDF generado y disponible en la vista previa.", {
        exact: true,
      }),
    ).toBeVisible({ timeout: 60000 });
    const download = page.waitForEvent("download");
    await page.getByRole("button", { name: /Descargar PDF/ }).click();
    await (await download).saveAs(resolve(output, "streamlit-original.pdf"));
    await shot("streamlit-pdf");
  }
  await page.goto(
    settings.instances.react.url +
      "/study/notebook/cpi/" +
      settings.original_note_id,
  );
  await expect(
    page.getByLabel("Título de la nota", { exact: true }),
  ).toHaveValue(/^Google Drive y Docs: comprender, producir e integrar/);
  await scaled("react-cpi");
  if (phase === "after") {
    await page.getByText("Imágenes de esta nota", { exact: true }).click();
    await expect(page.locator(".study-note-images img")).toHaveCount(6);
    await expect
      .poll(() =>
        page
          .locator(".study-note-images img")
          .evaluateAll((nodes) =>
            nodes.every((n) => n.complete && n.naturalWidth > 0),
          ),
      )
      .toBe(true);
    await shot("react-images");
    await page
      .getByLabel("Título de la nota", { exact: true })
      .fill(
        "Google Drive y Docs: comprender, producir e integrar — comprobado " +
          browserName,
      );
    await button("Guardar nota CPI").click();
    await expect(page.getByText(/Nota guardada y confirmada/)).toBeVisible();
    await page.reload();
    await expect(
      page.getByLabel("Título de la nota", { exact: true }),
    ).toHaveValue(
      "Google Drive y Docs: comprender, producir e integrar — comprobado " +
        browserName,
    );
  }
  const pdf = page.waitForEvent("download");
  await button("Exportar PDF").click();
  await (await pdf).saveAs(resolve(output, "react-" + phase + ".pdf"));
  const tex = page.waitForEvent("download");
  await button("Exportar proyecto TEX").click();
  await (await tex).saveAs(resolve(output, "react-" + phase + ".zip"));
  await shot("react-export");
  proof.passed = true;
} catch (error) {
  proof.passed = false;
  proof.error = String(error);
  await shot("failure");
  throw error;
} finally {
  await writeFile(
    resolve(output, "browser.json"),
    JSON.stringify(proof, null, 2),
  );
  await browser.close();
}
