import test from "node:test";
import {chromium,firefox,expect} from "@playwright/test";
import {readFile,writeFile} from "node:fs/promises";
import {browserCoverage} from "./browser-coverage.mjs";

await test("independent note creation, citation, lost reply and concurrent readback",{timeout:150000},async()=>{
  const name=process.env.MATHMONGO_STUDY_BROWSER??"chrome",base=process.env.MATHMONGO_INDEPENDENT_URL,evidence=process.env.MATHMONGO_INDEPENDENT_EVIDENCE;
  const source=JSON.parse(await readFile(evidence+"/authoring-browser.json","utf8"));
  const browser=name==="firefox"?await firefox.launch({headless:true}):await chromium.launch({headless:true,executablePath:"/usr/bin/google-chrome",args:["--no-sandbox"]});
  const page=await browser.newPage({viewport:{width:1440,height:1080},reducedMotion:"reduce"});
  const coverage=await browserCoverage(page,name,"notes");let passed=false;
  const errors=[];page.on("pageerror",error=>errors.push(error.message));page.setDefaultTimeout(20000);
  const editor=page.locator(".visual-document .tiptap");
  try{
    await coverage.goto(base+"/study/notes");
    await page.getByRole("link",{name:"+ Crear nota",exact:true}).click();
    await page.getByLabel("Nombre de la nota",{exact:true}).fill("Nota independiente con cita");
    await editor.fill("Mi texto antes de seleccionar una fuente.");
    await page.getByRole("button",{name:"Guardar nota",exact:true}).click();
    await expect(page.getByRole("status").filter({hasText:"elige una fuente"})).toBeVisible();
    await expect(editor).toContainText("antes de seleccionar");
    await page.getByRole("combobox",{name:"Fuente administrada",exact:true}).selectOption(source.sourceId);
    await page.getByText("Referencia y localizador",{exact:true}).click();
    await page.getByRole("combobox",{name:"Referencia bibliográfica",exact:true}).selectOption({label:"Referencia creada desde React"});
    await page.getByRole("textbox",{name:"Página impresa",exact:true}).fill("23");
    await coverage.reload();
    await expect(editor).toContainText("Mi texto antes");
    await page.getByText("Referencia y localizador",{exact:true}).click();
    await expect(page.getByRole("textbox",{name:"Página impresa",exact:true})).toHaveValue("23");
    let lost=false;
    await page.route(/\/api\/study\/v1\/operations$/u,async route=>{
      if(!lost){lost=true;const result=await route.fetch();expect((await result.json()).status).toBe("saved");await route.abort("failed");}else await route.continue();
    });
    await page.getByRole("button",{name:"Guardar nota",exact:true}).click();
    await expect(page.getByRole("button",{name:"Reintentar el mismo envío",exact:true})).toBeEnabled();
    await coverage.reload();
    await page.getByRole("button",{name:"Reintentar el mismo envío",exact:true}).click();
    await expect(page).toHaveURL(/\/study\/notes\/note_/u);
    const noteId=decodeURIComponent(new URL(page.url()).pathname.split('/').at(-1));
    await expect(page.getByRole("heading",{name:"Editar nota",exact:true})).toBeVisible();
    await page.unroute(/\/api\/study\/v1\/operations$/u);
    await editor.fill("Mi modificación conservada ante una carrera.");
    let raced=false;
    await page.route(new RegExp('/api/study/v1/notes/'+noteId+'$','u'),async route=>{
      if(raced){await route.continue();return;}raced=true;
      const before=await (await route.fetch()).json();
      const scope=await (await page.request.get(base+"/api/study/v1/context")).json();
      const response=await page.request.post(base+"/api/study/v1/operations",{headers:{Origin:base,"X-MathMongo-Library":scope.library_id},data:{action:"save_note",operation_id:crypto.randomUUID(),note_id:noteId,source_id:before.source_id,titulo:before.title,contenido_latex:"Cambio posterior de otra ventana.",revision:before.revision,reference_id:before.reference_id,reference_locator:before.reference_locator}});
      expect((await response.json()).status).toBe("saved");await route.continue();
    });
    await page.getByRole("button",{name:"Guardar nota",exact:true}).click();
    await expect(page.getByRole("status").filter({hasText:"cambió después del envío"})).toBeVisible();
    await expect(editor).toContainText("Mi modificación conservada");
    await expect(page.getByRole("button",{name:"Guardar nota",exact:true})).toBeDisabled();
    await page.screenshot({path:evidence+"/note-concurrent-readback.png",fullPage:true});
    await page.getByRole("button",{name:"Abrir versión guardada; conservar mi borrador",exact:true}).click();
    await expect(editor).toContainText("Cambio posterior de otra ventana");
    const retained=await page.evaluate(()=>Object.keys(localStorage).filter(key=>key.includes('study-documents')).flatMap(key=>Object.values(JSON.parse(localStorage.getItem(key)))).some(draft=>draft.content.includes('Mi modificación conservada')));
    expect(retained).toBe(true);
    await coverage.goto(base+"/study/notes");
    await page.getByRole("searchbox",{name:"Buscar notas por título",exact:true}).fill("independiente con cita");
    await page.getByRole("button",{name:"Buscar notas",exact:true}).click();
    await page.getByRole("link",{name:"Nota independiente con cita",exact:true}).last().click();
    await expect(page.getByRole("heading",{name:"Editar nota",exact:true})).toBeVisible();
    expect(errors).toEqual([]);
    passed=true;await writeFile(evidence+"/notes-browser.json",JSON.stringify({passed,browser:name,version:browser.version(),noteId,sourceId:source.sourceId,lostAcknowledgementRecovered:true,concurrentVersionPreserved:true,errors},null,2));
  }finally{await coverage.finish(passed);await browser.close();}
});
