/** Record actual visible menus and notebook tools, not just route definitions. */
import { expect } from "@playwright/test";
import { mkdir, readFile, writeFile } from "node:fs/promises";
import { resolve } from "node:path";
import { firefoxAtZoom } from "./firefox-native-zoom.mjs";
const base = resolve("../../evidence/sonar/cpi-five-images-2026-11-24"),
  own = JSON.parse(
    await readFile(resolve(base, "owned-comparison.json"), "utf8"),
  ),
  phase = process.env.MATHMONGO_COMPARE_PHASE || "before",
  output = resolve(base, "menus-" + phase);
await mkdir(output, { recursive: true, mode: 0o700 });
const browser = await firefoxAtZoom(
    own.instances.react.url + "/study",
    100,
    output,
  ),
  proof = { phase, clips: [], errors: [] };
async function clip(name, operation) {
  const page = await browser.context.newPage();
  page.setDefaultTimeout(25000);
  const started = Date.now(),
    events = [];
  page.on("pageerror", (error) =>
    proof.errors.push({ clip: name, message: error.message }),
  );
  try {
    await operation(page, async (label) => {
      events.push({ seconds: (Date.now() - started) / 1000, label });
      await page.screenshot({
        path: resolve(output, name + "-" + events.length + ".png"),
        fullPage: true,
      });
      await page.waitForTimeout(700);
    });
    await writeFile(
      resolve(output, name + "-accessibility.yml"),
      await page.locator("body").ariaSnapshot(),
    );
  } finally {
    await page.close();
    await page.video().saveAs(resolve(output, name + ".webm"));
    proof.clips.push({
      name,
      events,
      duration_seconds: (Date.now() - started) / 1000,
    });
  }
}
async function nav(page, text) {
  const control = page.getByRole("combobox", {
    name: "Navegación",
    exact: true,
  });
  await control.focus();
  await control.fill(text);
  await control.press("ArrowDown");
  await control.press("Enter");
}
try {
  await clip("streamlit-menu", async (page, mark) => {
    await page.goto(own.instances.streamlit.url);
    const control = page.getByRole("combobox", {
      name: "Navegación",
      exact: true,
    });
    await expect(control).toBeVisible({ timeout: 60000 });
    await control.focus();
    await control.fill("");
    await control.press("ArrowDown");
    proof.streamlit_menu = await page.getByRole("option").allTextContents();
    await mark("All available main options");
    await page.keyboard.press("Escape");
    proof.connection_controls = await page.getByTestId("stSidebar").innerText();
    await mark(
      "Connection controls available in this fixed comparison connection",
    );
  });
  for (const activity of [
    "Worklog",
    "Backlog",
    "Weekly Review",
    "Deliverables",
    "Kanban",
    "Diario",
  ])
    await clip(
      "streamlit-" + activity.toLowerCase().replaceAll(" ", "-"),
      async (page, mark) => {
        await page.goto(own.instances.streamlit.url);
        await expect(
          page.getByRole("combobox", { name: "Navegación", exact: true }),
        ).toBeVisible({ timeout: 60000 });
        await nav(page, "Cuaderno");
        await page.getByRole("tab", { name: activity, exact: true }).click();
        await mark(activity + " tools and forms");
        const panel = page.getByRole("tabpanel", {
          name: activity,
          exact: true,
        });
        await panel.locator("button:visible").last().scrollIntoViewIfNeeded();
        await mark(activity + " lower controls");
        if (activity === "Diario") {
          proof.diary_sections = await panel.getByRole("tab").allTextContents();
          for (const name of [
            "Buscar",
            "Timeline",
            "Calendario",
            "Proyectos",
            "Exportar",
            "Promover",
          ]) {
            await panel.getByRole("tab").filter({ hasText: name }).click();
            await mark("Diario " + name);
          }
        }
      },
    );
  await clip("streamlit-cornell-cpi", async (page, mark) => {
    await page.goto(own.instances.streamlit.url);
    await expect(
      page.getByRole("combobox", { name: "Navegación", exact: true }),
    ).toBeVisible({ timeout: 60000 });
    for (const name of ["Cornell", "CPI"]) {
      await nav(page, name);
      await mark(name + " direct menu");
    }
  });
  await clip("react-menu", async (page, mark) => {
    await page.goto(own.instances.react.url + "/study");
    await expect(
      page.getByRole("navigation", { name: "Navegación principal" }),
    ).toBeVisible();
    proof.react_links = await page
      .getByRole("navigation", { name: "Navegación principal" })
      .getByRole("link")
      .evaluateAll((nodes) =>
        nodes.map((n) => ({
          name: n.textContent,
          path: n.getAttribute("href"),
        })),
      );
    await mark("Visible React navigation");
    await page.getByRole("link", { name: "Cuaderno", exact: true }).click();
    await mark("React notebook entry");
    for (const name of ["Abrir Cornell", "Abrir CPI"]) {
      const link = page.getByRole("link", { name, exact: true });
      if (await link.count()) {
        await link.click();
        await mark(name);
        await page.goto(own.instances.react.url + "/study/notebook");
      }
    }
  });
  proof.passed = true;
} catch (error) {
  proof.passed = false;
  proof.error = String(error);
  throw error;
} finally {
  await writeFile(
    resolve(output, "menu-proof.json"),
    JSON.stringify(proof, null, 2),
  );
  await browser.close();
}
