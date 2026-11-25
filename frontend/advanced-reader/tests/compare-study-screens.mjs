/** Same historical cases in Streamlit and the real React routes, before/after presentation. */
import { expect } from "@playwright/test";
import { readFile, mkdir, writeFile } from "node:fs/promises";
import { resolve } from "node:path";
import { firefoxAtZoom } from "./firefox-native-zoom.mjs";
import test from "node:test";
await test("compare-study-screens", { timeout: 900000 }, async () => {
  const directory = resolve("../../evidence/sonar/cpi-five-images-2026-11-24"),
    own = JSON.parse(
      await readFile(resolve(directory, "owned-comparison.json"), "utf8"),
    );
  const phase = process.env.MATHMONGO_COMPARE_PHASE || "before",
    percent = Number(process.env.MATHMONGO_ZOOM || 100),
    out = resolve(directory, "screens-" + phase + "-firefox-" + percent);
  await mkdir(out, { recursive: true });
  const owned = await firefoxAtZoom(
      own.instances.react.url + "/study",
      percent,
    ),
    page = await owned.context.newPage(),
    errors = [],
    network = [],
    proof = { phase, percent, errors, network, views: [] };
  page.setDefaultTimeout(20000);
  page.on("pageerror", (error) => errors.push(error.message));
  page.on("response", (response) => {
    if (response.status() >= 400)
      network.push({ url: response.url(), status: response.status() });
  });
  async function shot(name) {
    await page.screenshot({
      path: resolve(out, name + ".png"),
      fullPage: true,
    });
    proof.views.push({
      name,
      ...(await page.evaluate(() => ({
        width: innerWidth,
        dpr: devicePixelRatio,
      }))),
    });
  }
  async function activate(locator) {
    await locator.focus();
    await locator.press("Enter");
  }
  async function nav(name) {
    const n = page.getByRole("combobox", { name: "Navegación", exact: true });
    await n.focus();
    await n.fill(name);
    await n.press("ArrowDown");
    await n.press("Enter");
  }
  try {
    await page.goto(own.instances.streamlit.url);
    await expect(
      page.getByRole("combobox", { name: "Navegación", exact: true }),
    ).toBeVisible({ timeout: 60000 });
    await shot("streamlit-home");
    await nav("Edit Source");
    await expect(
      page.getByRole("combobox", { name: "Source", exact: true }),
    ).toBeVisible();
    await page.getByRole("combobox", { name: "Source", exact: true }).focus();
    await page
      .getByRole("combobox", { name: "Source", exact: true })
      .press("ArrowDown");
    await shot("streamlit-library");
    await page.keyboard.press("Escape");
    await nav("Conceptos");
    await page
      .getByRole("textbox", { name: "Search", exact: true })
      .fill("Campos");
    await page
      .locator("summary")
      .filter({ hasText: "Campos (" })
      .press("Enter");
    await expect(
      page.getByRole("heading", { name: "LaTeX Content", exact: true }),
    ).toBeVisible();
    await shot("streamlit-campos");
    await page.goto(own.instances.react.url + "/study");
    await expect(
      page.getByRole("heading", {
        name: "Leer, escribir, conectar",
        exact: true,
      }),
    ).toBeVisible();
    await shot("react-home");
    await page.goto(own.instances.react.url + "/study/library");
    await expect(
      page.getByRole("heading", { name: "Tu biblioteca", exact: true }),
    ).toBeVisible();
    await expect(page.getByText(/fuentes encontradas/)).toBeVisible();
    await shot("react-library");
    await page.goto(
      own.instances.react.url +
        "/study/concepts/" +
        encodeURIComponent(own.campos.key),
    );
    await expect(
      page.getByRole("heading", { name: "Campos", exact: true }),
    ).toBeVisible();
    await expect(page.locator("math-field").first()).toBeVisible();
    await shot("react-campos");
    if (phase === "after") {
      await activate(
        page.getByRole("button", { name: "Ocultar contexto", exact: true }),
      );
      await expect(
        page.getByRole("button", { name: "Mostrar contexto", exact: true }),
      ).toBeVisible();
      await page.reload();
      await expect(
        page.getByRole("button", { name: "Mostrar contexto", exact: true }),
      ).toBeVisible();
      await shot("react-campos-clean");
      await activate(
        page.getByRole("button", { name: "Mostrar contexto", exact: true }),
      );
      await activate(
        page.getByRole("link", { name: "Biblioteca", exact: true }),
      );
      await activate(
        page.getByRole("button", { name: "Lista compacta", exact: true }),
      );
      await page.reload();
      await expect(
        page.getByRole("button", { name: "Lista compacta", exact: true }),
      ).toHaveAttribute("aria-pressed", "true");
      await shot("react-library-compact");
      await activate(page.getByRole("button", {name:"Ocultar navegación",exact:true}));
      await expect(page.getByRole("navigation", {name:"Navegación principal",exact:true}).getByRole("link", {name:"Worklog",exact:true})).toBeVisible();
      await activate(page.getByRole("button", {name:"Mostrar navegación",exact:true}));
      await page.setViewportSize({width:390,height:844});
      for(const [name,path] of [["home","/study"],["library","/study/library"],["campos","/study/concepts/"+encodeURIComponent(own.campos.key)]]) {
        await page.goto(own.instances.react.url+path);
        await expect(page.locator("h1")).toBeVisible();
        if(name==="campos")await expect(page.locator("math-field").first()).toBeVisible();
        const geometry=await page.evaluate(()=>({viewport:innerWidth,document:document.documentElement.scrollWidth}));
        expect(geometry.document).toBeLessThanOrEqual(geometry.viewport+1);
        await shot("react-"+name+"-narrow");
      }
    }
    proof.passed = true;
  } catch (error) {
    proof.passed = false;
    proof.error = String(error);
    await shot("failure");
    throw error;
  } finally {
    await writeFile(
      resolve(out, "browser.json"),
      JSON.stringify(proof, null, 2),
    );
    await owned.close();
  }
});
