import { chromium, firefox, expect, test } from "@playwright/test";
import { writeFile } from "node:fs/promises";
test("study sphere real application", async () => {
  const evidence = process.env.MATHMONGO_MAP_TEST_EVIDENCE,
    phase = process.env.MATHMONGO_STUDY_PHASE;
  const browserName = process.env.MATHMONGO_STUDY_BROWSER ?? "chrome";
  const browser =
    browserName === "firefox"
      ? await firefox.launch({ headless: true })
      : await chromium.launch({
          executablePath: "/usr/bin/google-chrome",
          headless: true,
          args: ["--no-sandbox"],
        });
  const context = await browser.newContext({
    viewport: { width: 1366, height: 768 },
    deviceScaleFactor: 1,
    reducedMotion: "reduce",
    hasTouch: browserName === "chrome",
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
    await nav.click({ timeout: 60000 });
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
        await map.locator("canvas").evaluate((canvas) => ({
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
        await map.locator("canvas").evaluate((canvas) => ({
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
    await progress(
      "template:" +
        JSON.stringify(
          await editor
            .locator("math-field")
            .evaluateAll((fs) =>
              fs.map((f) => ({ value: f.value, focus: f.hasFocus() })),
            ),
        ),
    );
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
    await expect
      .poll(() =>
        editor
          .locator("math-field")
          .last()
          .evaluate((f) => f.getRootNode().activeElement === f),
      )
      .toBe(true);
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
    const keyboardToggle = editor
      .locator("math-field")
      .first()
      .locator('[part="virtual-keyboard-toggle"]');
    await keyboardToggle.click();
    const keyboard = editor.locator(".ML__keyboard");
    await expect(keyboard).toBeVisible();
    const keyboardStyle = await keyboard.evaluate((el) => ({
      width: el.getBoundingClientRect().width,
      height: el.getBoundingClientRect().height,
      position: getComputedStyle(el).position,
      background: getComputedStyle(el.querySelector(".MLK__backdrop"))
        .backgroundColor,
    }));
    await progress("keyboard:" + JSON.stringify(keyboardStyle));
    const formula = editor.locator('math-field').first();
    const beforeVirtual = await formula.evaluate(field => field.value);
    await keyboard.locator('.MLK__layer:visible [data-keycap-value="7"]').first().click();
    const afterVirtual = await formula.evaluate(field => field.value);
    expect(afterVirtual).not.toBe(beforeVirtual);
    await keyboard.locator('.MLK__layer:visible [data-command=\'"undo"\']').click();
    expect(await formula.evaluate(field => field.value)).not.toBe(afterVirtual);
    await keyboard.locator('.MLK__layer:visible [data-command=\'"redo"\']').click();
    expect(await formula.evaluate(field => field.value)).toBe(afterVirtual);
    await page.keyboard.press('Backspace');
    await expect.poll(() => formula.evaluate(field => field.value)).toBe(beforeVirtual);
    const layoutNames = [];
    for (const index of [1, 2, 3, 0]) {
      const choices = keyboard.locator('.MLK__layer:visible .MLK__toolbar .left > div');
      layoutNames.push(await choices.nth(index).getAttribute('data-tooltip'));
      await choices.nth(index).click();
      await expect.poll(()=>editor.evaluate(el=>{
        const host=el.querySelector('.math-keyboard-host');
        const plate=window.mathVirtualKeyboard.boundingRect;
        const close=host.querySelector('button').getBoundingClientRect();
        return {spacing:host.getBoundingClientRect().height-plate.height, clear:plate.top>=close.bottom};
      })).toMatchObject({clear:true});
      const space=await editor.evaluate(el=>el.querySelector('.math-keyboard-host').getBoundingClientRect().height-window.mathVirtualKeyboard.boundingRect.height);
      expect(space).toBeLessThan(70);

    }
    const seven = keyboard.locator('.MLK__layer:visible [data-keycap-value="7"]').first();
    await seven.hover(); await page.mouse.down();
    const variants = keyboard.locator('.MLK__variant-panel');
    await expect(variants).toBeVisible();
    expect(await variants.locator('.item').count()).toBeGreaterThan(1);
    expect(await variants.evaluate(el => getComputedStyle(el).backgroundColor)).toBe('rgb(16, 39, 55)');
    // MathLive installs the variant pointer handlers on its next animation frame.
    await page.evaluate(() => new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve))));
    await variants.locator('.item').first().hover();
    await page.mouse.up();
    await expect(variants).not.toBeVisible();
    await expect.poll(() => formula.evaluate(field => field.value)).toContain('\\frac17');
    await keyboard.locator('.MLK__layer:visible [data-command=\'"undo"\']').click();
    await expect.poll(() => formula.evaluate(field => field.value)).toBe(afterVirtual);
    await page.keyboard.press('Backspace');
    await expect.poll(() => formula.evaluate(field => field.value)).toBe(beforeVirtual);
    await progress('virtual-key-edit-undo-redo-layouts:' + JSON.stringify(layoutNames));
    await editor.screenshot({ path: `${evidence}/after-math-keyboard.png` });
    expect(keyboardStyle.position).toBe("relative");
    expect(keyboardStyle.height).toBeLessThanOrEqual(400);
    expect(keyboardStyle.background).toBe("rgb(9, 26, 39)");
    await editor
      .getByRole("button", { name: "Ocultar teclado matemático", exact: true })
      .click();
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
    await progress(
      "template:" +
        JSON.stringify(
          await editor
            .locator("math-field")
            .evaluateAll((fs) =>
              fs.map((f) => ({ value: f.value, focus: f.hasFocus() })),
            ),
        ),
    );
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
    await progress(
      "recoveryFocus:" +
        JSON.stringify(
          await editor
            .locator("math-field")
            .evaluateAll((fs) =>
              fs.map((f) => ({
                value: f.value,
                focus: f.hasFocus(),
                active: f.getRootNode().activeElement?.tagName,
              })),
            ),
        ),
    );
    await expect
      .poll(() =>
        editor
          .locator("math-field")
          .last()
          .evaluate((f) => f.getRootNode().activeElement === f),
      )
      .toBe(true);
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
    await editor.getByRole('button', { name: 'Buscar o añadir referencia', exact: true }).click();
    let picker = page.getByRole('dialog', { name: 'Referencias del documento', exact: true });
    await picker.getByRole('textbox', { name: 'Pegar DOI o ISBN', exact: true }).fill('10.9999/missing');
    await picker.getByRole('button', { name: 'Buscar referencia', exact: true }).click();
    await expect(picker.getByRole('status')).toContainText('No se pudo recuperar');
    await picker.getByRole('textbox', { name: 'Pegar DOI o ISBN', exact: true }).fill('10.9999/outage');
    await picker.getByRole('button', { name: 'Buscar referencia', exact: true }).click();
    await expect(picker.getByRole('status')).toContainText('no disponible');
    await picker.getByRole('textbox', { name: 'Pegar DOI o ISBN', exact: true }).fill('https://doi.org/10.1007/BF01106749');
    await picker.getByRole('button', { name: 'Buscar referencia', exact: true }).click();
    await expect(picker.getByRole('status')).toContainText('Ficha recuperada');
    await picker.getByRole('button', { name: 'Revisar esta propuesta', exact: true }).click();
    await picker.getByRole('textbox', { name: 'Título de la referencia', exact: true }).fill('Corrección de la propuesta temporal');
    await picker.getByRole('button', { name: 'Guardar ficha y citar', exact: true }).click();
    await expect(picker.getByRole('status')).toContainText('coincidencias locales');
    await picker.getByRole('button', { name: 'Usar referencia existente', exact: true }).click();
    await picker.getByRole('button', { name: 'Guardar ficha y citar', exact: true }).click();
    await expect(picker).toHaveCount(0);
    await expect(editor.locator('.document-citation')).toContainText('Ficha local corregida de Nyaga');
    await editor.getByText('Localizador de este pasaje', { exact: true }).click();
    await editor.getByRole('textbox', { name: 'Página impresa', exact: true }).fill('229');
    await editor.getByRole('textbox', { name: 'Página física del PDF (sin deducir página impresa)', exact: true }).fill('3');
    await editor.screenshot({ path: `${evidence}/after-citation.png` });
    await progress('citation-existing-id-preserved-document-recovered');
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
    const legacyKey = process.env.MATHMONGO_STUDY_PRIVATE_KEY;
    if (legacyKey) {
      await map.getByRole('combobox', { name: 'Seleccionar concepto', exact: true }).selectOption(legacyKey);
      await map.getByRole('button', { name: 'Editar ficha', exact: true }).click();
      const legacyEditor = page.locator('.editor-dialog');
      await expect(legacyEditor.locator('.visual-document')).toBeVisible();
      await legacyEditor.getByRole('button', { name: 'Guardar concepto', exact: true }).click();
      await expect(legacyEditor).toHaveCount(0);
      await progress('private-legacy-opened-and-saved-through-real-editor');
    }
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
