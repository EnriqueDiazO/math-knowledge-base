import { browserCoverage } from "./browser-coverage.mjs";
import test from "node:test";
import { chromium, firefox, expect } from "@playwright/test";
import { writeFile } from "node:fs/promises";

await test(
  "create a source, reference, PDF and concepts; edit and connect through React",
  { timeout: 150000 },
  async () => {
    const name = process.env.MATHMONGO_STUDY_BROWSER ?? "chrome",
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
    const context = await browser.newContext({
      viewport: { width: 1440, height: 1080 },
      reducedMotion: "reduce",
    });
    const page = await context.newPage();
    const coverage = await browserCoverage(page, name, "authoring");
    let passed = false;
    page.setDefaultTimeout(20000);
    const errors = [];
    page.on("pageerror", (error) => errors.push(error.message));
    const shot = async (name) =>
      page.screenshot({
        path: evidence + "/authoring-" + name + ".png",
        fullPage: true,
      });
    const read = async (path) =>
      page.evaluate(async (path) => {
        const context = await (await fetch("/api/study/v1/context")).json();
        const response = await fetch("/api/study/v1" + path, {
          headers: { "X-MathMongo-Library": context.library_id },
        });
        if (!response.ok) throw new Error("Readback failed");
        return response.json();
      }, path);
    try {
      await coverage.goto(base + "/study/library");
      await page
        .getByRole("link", { name: "+ Añadir fuente", exact: true })
        .click();
      await page
        .getByRole("textbox", { name: "Nombre de la fuente", exact: true })
        .fill("Fuente creada desde React");
      if(process.env.MATHMONGO_AUTHORING_PREPARE==="1"){
        await page.getByRole("button",{name:"Preparar biblioteca",exact:true}).click();
        await expect(page.getByRole("status").filter({hasText:"Biblioteca preparada"})).toBeVisible();
        expect((await read('/library?'+new URLSearchParams({q:'Fuente creada desde React'}))).total).toBe(0);
        await expect(page.getByRole("textbox",{name:"Nombre de la fuente",exact:true})).toHaveValue("Fuente creada desde React");
        await shot("preparation-retains-draft");
      }
      let lost = false;
      await page.route(/\/api\/study\/v1\/sources$/u, async (route) => {
        if (!lost) {
          lost = true;
          const result = await route.fetch();
          expect(result.ok()).toBe(true);
          await route.abort("failed");
        } else await route.continue();
      });
      await page
        .getByRole("button", { name: "Guardar fuente", exact: true })
        .click();
      await expect(
        page.getByRole("button", {
          name: "Reintentar el mismo envío",
          exact: true,
        }),
      ).toBeVisible();
      await coverage.reload();
      await page
        .getByRole("button", { name: "Reintentar el mismo envío", exact: true })
        .click();
      await expect(
        page.getByRole("heading", {
          name: "Fuente creada desde React",
          exact: true,
        }),
      ).toBeVisible();
      const sourceId = decodeURIComponent(
        new URL(page.url()).pathname.split("/").at(-1),
      );
      await shot("source-created");
      await page
        .getByRole("button", { name: "+ Añadir referencia", exact: true })
        .click();
      await page
        .getByRole("textbox", { name: "Título de la referencia", exact: true })
        .fill("Referencia creada desde React");
      await page
        .getByRole("textbox", { name: "Autor u organización", exact: true })
        .fill("Autora de prueba");
      await page
        .getByRole("spinbutton", { name: "Año de publicación", exact: true })
        .fill("2020");
      await page
        .getByRole("button", { name: "Guardar referencia", exact: true })
        .click();
      await expect(
        page.getByRole("heading", {
          name: "Referencia creada desde React",
          exact: true,
        }),
      ).toBeVisible();
      await shot("reference-saved");
      await page
        .getByRole("button", { name: "+ Asociar documento", exact: true })
        .click();
      await page
        .getByRole("textbox", { name: "Título del documento", exact: true })
        .fill("PDF asociado desde React");
      await page
        .getByRole("combobox", {
          name: "Referencia del documento",
          exact: true,
        })
        .selectOption({ label: "Referencia creada desde React" });
      await page
        .getByLabel("Archivo PDF", { exact: true })
        .setInputFiles(process.env.MATHMONGO_AUTHORING_PDF);
      await page
        .getByRole("button", { name: "Asociar documento", exact: true })
        .click();
      await expect(
        page.getByRole("heading", {
          name: "PDF asociado desde React",
          exact: true,
        }),
      ).toBeVisible();
      await shot("pdf-associated");
      await page
        .getByRole("link", {
          name: "+ Crear concepto desde esta fuente",
          exact: true,
        })
        .click();
      await page
        .getByRole("textbox", { name: "Nombre del concepto", exact: true })
        .fill("Definición creada desde React");
      await page
        .getByRole("textbox", { name: "Documento visual", exact: true })
        .fill("Una definición con una fórmula: ");
      await page
        .getByRole("button", { name: "Insertar fórmula en línea", exact: true })
        .click();
      const math = page.locator(".visual-document math-field").last();
      await math.evaluate((field) => {
        field.setValue("\\frac{1}{2}");
        field.dispatchEvent(new InputEvent("input", { bubbles: true }));
      });
      await page
        .getByText("Referencia y organización", { exact: true })
        .click();
      await page
        .getByRole("combobox", {
          name: "Referencia bibliográfica",
          exact: true,
        })
        .selectOption({ label: "Referencia creada desde React" });
      await page
        .getByRole("textbox", { name: "Localizador de página", exact: true })
        .fill("17");
      await shot("concept-before-save");
      await page
        .getByRole("button", { name: "Guardar concepto", exact: true })
        .click();
      await expect(
        page.getByRole("heading", {
          name: "Definición creada desde React",
          exact: true,
        }),
      ).toBeVisible();
      const firstKey = decodeURIComponent(
        new URL(page.url()).pathname.split("/").at(-1),
      );
      await coverage.reload();
      await page
        .getByRole("link", { name: "Editar concepto", exact: true })
        .click();
      await page
        .getByRole("textbox", { name: "Nombre del concepto", exact: true })
        .fill("Definición editada desde React");
      const visual = page.getByRole("textbox", {
        name: "Documento visual",
        exact: true,
      });
      await visual.click();
      await visual.press("Control+End");
      await page.keyboard.type(" Texto añadido al editar.");
      await expect(page.locator(".visual-document math-field")).toHaveCount(1);
      await page
        .getByRole("button", { name: "Guardar concepto", exact: true })
        .click();
      await expect(
        page.getByRole("heading", {
          name: "Definición editada desde React",
          exact: true,
        }),
      ).toBeVisible();
      await coverage.reload();
      const edited = await read(
        "/concepts/detail?" + new URLSearchParams({ key: firstKey }),
      );
      expect(edited.contenido_latex).toContain("\\frac{1}{2}");
      expect(edited.contenido_latex).toContain("Texto añadido al editar.");
      expect(edited.source_id).toBe(sourceId);
      expect(edited.reference_locator.printed_page).toBe("17");
      await shot("concept-edited-reloaded");
      await page
        .getByRole("link", { name: "Volver a Conceptos", exact: true })
        .click();
      await page
        .getByRole("link", { name: "+ Crear concepto", exact: true })
        .click();
      await page
        .getByRole("textbox", { name: "Nombre del concepto", exact: true })
        .fill("Segundo concepto relacionado");
      await page
        .getByRole("combobox", { name: "Fuente administrada", exact: true })
        .selectOption(sourceId);
      await page
        .getByRole("combobox", { name: "Tipo matemático", exact: true })
        .selectOption("teorema");
      await page
        .getByRole("textbox", { name: "Documento visual", exact: true })
        .fill("Una consecuencia para conectar.");
      await page
        .getByRole("button", { name: "Guardar concepto", exact: true })
        .click();
      await expect(
        page.getByRole("heading", {
          name: "Segundo concepto relacionado",
          exact: true,
        }),
      ).toBeVisible();
      const secondKey = decodeURIComponent(
        new URL(page.url()).pathname.split("/").at(-1),
      );
      await page
        .getByRole("combobox", { name: "Concepto relacionado", exact: true })
        .selectOption(firstKey);
      await page
        .getByRole("button", { name: "Guardar relación", exact: true })
        .click();
      await expect(
        page.getByRole("status").filter({ hasText: "vínculo confirmados" }),
      ).toBeVisible();
      await coverage.reload();
      const second = await read(
        "/concepts/detail?" + new URLSearchParams({ key: secondKey }),
      );
      const first = await read(
        "/concepts/detail?" + new URLSearchParams({ key: firstKey }),
      );
      expect(second.relations).toHaveLength(1);
      expect(first.relations).toEqual(second.relations);
      expect(second.relations[0]).toMatchObject({
        from: secondKey,
        to: firstKey,
        tipo: "requiere_concepto",
      });
      await shot("relationship-reloaded");
      await page
        .getByRole("link", { name: "Ver en una esfera", exact: true })
        .click();
      await expect(
        page.getByRole("button", { name: "Editar ficha", exact: true }),
      ).toBeVisible();
      await shot("sphere-new-concepts");
      await page
        .getByRole("button", { name: "Editar ficha", exact: true })
        .click();
      await expect(
        page.getByRole("heading", { name: "Editar concepto", exact: true }),
      ).toBeVisible();
      await coverage.goto(base + "/study/sources/new");
      await page
        .getByRole("textbox", { name: "Nombre de la fuente", exact: true })
        .fill("Página web sin identificadores");
      await page
        .getByRole("combobox", { name: "Tipo de fuente", exact: true })
        .selectOption("web");
      await page
        .getByRole("button", { name: "Guardar fuente", exact: true })
        .click();
      await expect(
        page.getByRole("heading", {
          name: "Página web sin identificadores",
          exact: true,
        }),
      ).toBeVisible();
      const webSourceId = decodeURIComponent(
        new URL(page.url()).pathname.split("/").at(-1),
      );
      await page
        .getByRole("button", { name: "+ Añadir referencia", exact: true })
        .click();
      await page
        .getByRole("combobox", { name: "Tipo de referencia", exact: true })
        .selectOption("web");
      await page
        .getByRole("textbox", { name: "Título de la referencia", exact: true })
        .fill("Página citada manualmente");
      await page
        .getByRole("textbox", { name: "URL", exact: true })
        .fill("https://example.org/academia");
      await page
        .getByRole("button", { name: "Guardar referencia", exact: true })
        .click();
      await expect(
        page.getByRole("heading", {
          name: "Página citada manualmente",
          exact: true,
        }),
      ).toBeVisible();
      await shot("web-without-doi-isbn");
      expect(errors).toEqual([]);
      await writeFile(
        evidence + "/authoring-browser.json",
        JSON.stringify(
          {
            browser: name,
            version: browser.version(),
            sourceId,
            webSourceId,
            firstKey,
            secondKey,
            sourceLostAcknowledgementRecovered: true,
            errors,
            passed: true,
          },
          null,
          2,
        ),
      );
      passed = true;
    } catch (error) {
      await writeFile(
        evidence + "/authoring-failure.txt",
        String(error) + "\n" + JSON.stringify(errors),
      );
      throw error;
    } finally {
      await coverage.finish(passed);
      await context.close();
      await browser.close();
    }
  },
);
