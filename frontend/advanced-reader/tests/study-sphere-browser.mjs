import { chromium, expect, test } from "@playwright/test";
import { writeFile } from "node:fs/promises";
test("study sphere real application", async () => {
  const evidence = process.env.MATHMONGO_MAP_TEST_EVIDENCE,
    phase = process.env.MATHMONGO_STUDY_PHASE;
  const browser = await chromium.launch({
    executablePath: "/usr/bin/google-chrome",
    headless: true,
    args: ["--no-sandbox"],
  });
  const context = await browser.newContext({
    viewport: { width: 1366, height: 768 },
    deviceScaleFactor: 1,
    reducedMotion: "reduce",
    hasTouch: true,
  });
  const page = await context.newPage();
  page.setDefaultTimeout(18000);
  const errors = [];
  page.on("pageerror", (error) => errors.push(error.message));
  await context.route("**/*", (route) =>
    ["127.0.0.1", "localhost"].includes(new URL(route.request().url()).hostname)
      ? route.continue()
      : route.abort(),
  );
  try {
    await page.goto(process.env.MATHMONGO_MAP_TEST_URL);
    const nav = page.getByRole("combobox", { name: "Navegación", exact: true });
    await nav.click({timeout:60000});
    await nav.fill("Grafo de conocimiento");
    await page
      .getByRole("option")
      .filter({ hasText: "Grafo de conocimiento" })
      .first()
      .click();
    const map = page.locator(".knowledge-map");
    await expect(map).toBeVisible();
    await map
      .getByLabel("Seleccionar concepto", { exact: true })
      .selectOption("nota:slow@Fuente de estudio temporal");
    const sizes = [];
    for (const [width, height] of [
      [1366, 768],
      [1920, 1080],
    ]) {
      await page.setViewportSize({ width, height });
      await map.locator("canvas").scrollIntoViewIfNeeded();
      sizes.push(
        await map
          .locator("canvas")
          .evaluate((canvas) => ({
            width: canvas.getBoundingClientRect().width,
            height: canvas.getBoundingClientRect().height,
            internalWidth: canvas.width,
            internalHeight: canvas.height,
            viewport: [innerWidth, innerHeight],
            dpr: devicePixelRatio,
          })),
      );
      await page.screenshot({ path: `${evidence}/${phase}-${width}.png` });
    }
    if (phase === "before") {
      await writeFile(
        `${evidence}/before-measures.json`,
        JSON.stringify(
          { sizes, errors, browser: await browser.version(), zoom: 100 },
          null,
          2,
        ) + "\n",
      );
      expect(errors).toEqual([]);
      return;
    }

    const progress = (label) =>
      writeFile(`${evidence}/after-progress.log`, label + "\n", { flag: "a" });
    const more = async () => {
      const details = map.locator(".extra-actions");
      if (!(await details.getAttribute("open")))
        await details.locator("summary").click();
    };
    await progress("initial");
    await map
      .getByRole("button", { name: "Expandir mapa", exact: true })
      .click();
    const expanded = [];
    for (const [width, height] of [
      [1366, 768],
      [1920, 1080],
    ]) {
      await page.setViewportSize({ width, height });
      await expect
        .poll(
          async () =>
            Number(
              await map.locator("canvas").getAttribute("data-css-height"),
            ) / height,
        )
        .toBeGreaterThanOrEqual(0.85);
      expanded.push(
        await map
          .locator("canvas")
          .evaluate((canvas) => ({
            width: canvas.getBoundingClientRect().width,
            height: canvas.getBoundingClientRect().height,
            internalWidth: canvas.width,
            internalHeight: canvas.height,
            viewport: [innerWidth, innerHeight],
          })),
      );
      await page.screenshot({
        path: `${evidence}/after-expanded-${width}.png`,
      });
    }
    await progress("expanded");
    await map
      .getByRole("button", { name: "Leer concepto", exact: true })
      .click();
    const reader = page.locator(".reader-dialog");
    await expect(
      reader.getByText("Definición: Slowly oscillating shift", { exact: true }),
    ).toBeVisible();
    await expect(reader.locator("math-field").first()).toBeVisible();
    await expect(reader.locator("pre").first()).toContainText("print(");
    await reader.screenshot({
      path: `${evidence}/after-mathematical-reading.png`,
    });
    await reader
      .getByRole("button", { name: "Cerrar lectura", exact: true })
      .click();
    await map
      .getByRole("button", { name: "Crear concepto aquí", exact: true })
      .click();
    let editor = page.locator(".editor-dialog");
    await editor
      .getByLabel("Nombre", { exact: true })
      .fill("Concepto visual confirmado");
    await editor
      .getByText("Metadatos, fuente y referencia", { exact: true })
      .click();
    await editor
      .getByLabel("Tipo de concepto", { exact: true })
      .selectOption("definicion");
    await editor
      .getByLabel("Insertar bloque de resultado", { exact: true })
      .selectOption("definition");
    await editor
      .locator(".visual-document section[data-result] p")
      .first()
      .click();
    await page.keyboard.type(
      "Prosa normal escrita visualmente, con una fraccion y una matriz. ",
    );
    await editor
      .getByRole("button", { name: "Insertar fórmula en línea", exact: true })
      .click();
    await editor.getByRole("button", { name: "Fracción", exact: true }).click();
    await progress("template:"+JSON.stringify(await editor.locator("math-field").evaluateAll(fs=>fs.map(f=>({value:f.value,focus:f.hasFocus()})))));
    await progress(
      "focus:" +
        JSON.stringify(
          await editor
            .locator("math-field")
            .last()
            .evaluate((field) => ({
              readOnly: field.readOnly,
              disabled: field.disabled,
              hasFocus: field.hasFocus(),
              outer: document.activeElement?.tagName,
              rootActive: field.getRootNode().activeElement?.tagName,
              inner: field.shadowRoot?.activeElement?.outerHTML?.slice(0, 1000),
            })),
        ),
    );
    await expect.poll(()=>editor.locator("math-field").last().evaluate(f=>f.getRootNode().activeElement === f)).toBe(true);
    await page.keyboard.type("1");
    await page.keyboard.press("ArrowDown");
    await page.keyboard.type("2");
    await progress(
      "fraction:" +
        (await editor
          .locator("math-field")
          .last()
          .evaluate((field) => field.value)),
    );
    await editor
      .getByRole("button", { name: "Volver al párrafo", exact: true })
      .click();
    await page.keyboard.type("También una matriz: ");
    await editor
      .getByRole("button", { name: "Insertar fórmula en bloque", exact: true })
      .click();
    await editor
      .getByRole("button", { name: "Matriz 2×2", exact: true })
      .click();
    await editor
      .getByRole("button", { name: "Insertar fórmula en línea", exact: true })
      .click();
    await editor.getByRole("button", { name: "Fracción", exact: true }).click();
    await progress("template:"+JSON.stringify(await editor.locator("math-field").evaluateAll(fs=>fs.map(f=>({value:f.value,focus:f.hasFocus()})))));
    await expect(editor.locator('[data-invalid="true"]').last()).toBeVisible();
    await editor
      .getByRole("button", { name: "Volver al párrafo", exact: true })
      .click();
    await page.keyboard.type(
      "Este parrafo sigue editable aunque la formula este incompleta.",
    );
    await editor.screenshot({ path: `${evidence}/after-incomplete-draft.png` });
    await editor
      .getByRole("button", { name: "Conservar borrador y volver", exact: true })
      .click();
    await page.reload();
    const again = page.getByRole("combobox", {
      name: "Navegación",
      exact: true,
    });
    await again.click();
    await again.fill("Grafo de conocimiento");
    await page
      .getByRole("option")
      .filter({ hasText: "Grafo de conocimiento" })
      .first()
      .click();
    await more();
    await map
      .getByRole("button", { name: "Recuperar borradores", exact: true })
      .click();
    await page
      .locator(".drafts-dialog")
      .getByRole("button", { name: /Concepto visual confirmado/ })
      .click();
    editor = page.locator(".editor-dialog");
    await expect(editor.getByLabel("Nombre", { exact: true })).toHaveValue(
      "Concepto visual confirmado",
    );
    await expect(editor.locator(".visual-document")).toContainText(
      "Este parrafo sigue editable",
    );
    await editor
      .locator("math-field")
      .last()
      .click({ position: { x: 15, y: 12 } });
    await progress("recoveryFocus:"+JSON.stringify(await editor.locator("math-field").evaluateAll(fs=>fs.map(f=>({value:f.value,focus:f.hasFocus(),active:f.getRootNode().activeElement?.tagName})))));
    await expect.poll(()=>editor.locator("math-field").last().evaluate(f=>f.getRootNode().activeElement === f)).toBe(true);
    await page.keyboard.type("3");
    await page.keyboard.press("ArrowDown");
    await page.keyboard.type("4");
    await progress(
      "corrected:" +
        (await editor
          .locator("math-field")
          .last()
          .evaluate((field) => field.value)),
    );
    await expect(editor.locator('[data-invalid="true"]')).toHaveCount(0);
    await editor
      .getByRole("button", { name: "Guardar concepto", exact: true })
      .click();
    await expect(page.locator(".editor-dialog")).toHaveCount(0);
    await expect(
      map.getByRole("heading", {
        name: "Concepto visual confirmado",
        exact: true,
      }),
    ).toBeVisible();
    await progress("saved");
    expect(errors).toEqual([]);
    await writeFile(
      `${evidence}/after-browser.json`,
      JSON.stringify(
        {
          sizes,
          expanded,
          errors,
          browser: await browser.version(),
          zoom: 100,
        },
        null,
        2,
      ) + "\n",
    );
  } catch (error) {
    await page.screenshot({
      path: `${evidence}/${phase}-failure.png`,
      fullPage: true,
    });
    console.error(await page.locator("body").innerText());
    throw error;
  } finally {
    await browser.close();
  }
});
