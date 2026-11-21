import { chromium, expect, test } from '@playwright/test';
import { writeFile } from 'node:fs/promises';
test('map persistence and real local rendering', async () => {
const url = process.env.MATHMONGO_MAP_TEST_URL;
const evidence = process.env.MATHMONGO_MAP_TEST_EVIDENCE;
const mode = process.env.MATHMONGO_MAP_TEST_MODE;
const browser = await chromium.launch({ executablePath: '/usr/bin/google-chrome', headless: true, args: ['--no-sandbox'] });
const context = await browser.newContext({ viewport: { width: 1440, height: 1100 }, reducedMotion: 'reduce', hasTouch: true });
const page = await context.newPage();
page.setDefaultTimeout(15000); page.setDefaultNavigationTimeout(20000);
const progress = text => writeFile(`${evidence}/progress-${mode ?? 'flow'}.log`, text + '\n', {flag:'a'});
const errors = [], remote = [], consoleErrors = [];
page.on('console', message => { if (message.type() === 'error') consoleErrors.push(message.text()); });
page.on('pageerror', error => errors.push(error.message));
await context.route('**/*', route => { const address = new URL(route.request().url()); if (!['127.0.0.1', 'localhost'].includes(address.hostname)) { remote.push(address.origin + address.pathname); return route.abort(); } return route.continue(); });
const screenshot = name => page.locator('.knowledge-map').screenshot({ path: `${evidence}/${name}.png` });
async function navigate(label) {
  const combo = page.getByRole('combobox', { name: 'Navegación', exact: true });
  if (!(await combo.isVisible()) || (await combo.boundingBox())?.x < 0) {
    const open = page.getByRole('button', { name: /Open sidebar|Expand sidebar|Abrir.*barra/ });
    if (await open.first().isVisible()) await open.first().click();
  }
  await combo.click(); await page.getByRole('option', { name: label, exact: true }).click();
}
try {
  await progress('start'); await page.goto(url); await progress('loaded'); await navigate('🗺️ Grafo de conocimiento');
  await expect(page.getByRole('heading', { name: 'Tu conocimiento, conectado' })).toBeVisible({ timeout: 30000 });
  if (mode === 'performance') {
    const canvas = page.locator('.knowledge-map canvas');
    await canvas.scrollIntoViewIfNeeded(); await canvas.focus();
    const samples = [];
    for (let i = 0; i < 25; i++) { await page.keyboard.press('ArrowRight'); await page.evaluate(() => new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve)))); if (i >= 5) samples.push(Number(await canvas.getAttribute('data-render-ms'))); }
    const summary = { graph_nodes: Number(await canvas.getAttribute('data-nodes')), graph_edges: Number(await canvas.getAttribute('data-edges')), measured_frames: samples.length, mean_render_ms: samples.reduce((a,b)=>a+b,0)/samples.length, max_render_ms: Math.max(...samples), min_render_ms: Math.min(...samples), device_pixel_ratio: await page.evaluate(()=>devicePixelRatio), page_errors: errors, console_errors: consoleErrors, blocked_host_icon_requests: remote, browser: await browser.version(), viewport:'1440x1100', reduced_motion:true };
    await page.locator('.knowledge-map').screenshot({path:`${evidence}/07-performance.png`});
    await writeFile(`${evidence}/performance.json`, JSON.stringify(summary,null,2)+'\n');
    if(errors.length || summary.graph_nodes < 1000) throw new Error('Performance case was not rendered correctly');
    console.log(JSON.stringify(summary));
  } else {
  await progress('initial'); await screenshot('01-initial');
  const map = page.locator('.knowledge-map');
  await map.getByRole('button', { name: 'Crear concepto aquí', exact: true }).click();
  await map.getByLabel('Nombre', { exact: true }).fill('Grupo creado desde la esfera');
  await map.getByLabel('Contenido (texto o LaTeX)', { exact: true }).fill('$G$ es un grupo.');
  await map.getByRole('button', { name: 'Guardar', exact: true }).click();
  await expect(map.getByRole('heading', { name: 'Grupo creado desde la esfera', exact: true })).toBeVisible();
  await progress('created'); await screenshot('02-created');
  await map.getByRole('button', { name: 'Conectar con…', exact: true }).click();
  await map.getByLabel('Destino', { exact: true }).selectOption(await map.getByLabel('Destino', { exact: true }).evaluate(select => [...select.options].find(o => o.textContent.includes('Idea semilla'))?.value));
  await map.getByLabel('Tipo de relación', { exact: true }).selectOption('implica');
  await map.getByRole('button', { name: 'Guardar', exact: true }).click();
  await expect(map.locator('canvas')).toHaveAttribute('data-edges', '1');
  // After connecting, return to the created concept using a local search.
  await map.getByLabel('Seleccionar concepto', { exact: true }).selectOption(await map.getByLabel('Seleccionar concepto', { exact: true }).evaluate(select => [...select.options].find(o => o.textContent.includes('Grupo creado desde'))?.value));
  await map.getByRole('button', { name: 'Editar ficha', exact: true }).click();
  await map.getByLabel('Nombre', { exact: true }).fill('Grupo editado desde la esfera');
  await map.getByLabel('Contenido (texto o LaTeX)', { exact: true }).fill('$G \\times G \\to G$; edición persistida.');
  await map.getByRole('button', { name: 'Guardar', exact: true }).click();
  await expect(map.getByRole('heading', { name: 'Grupo editado desde la esfera', exact: true })).toBeVisible();
  await progress('edited'); await screenshot('03-edited');
  await page.reload(); await navigate('🗺️ Grafo de conocimiento');
  await expect(map.getByRole('heading', { name: 'Grupo editado desde la esfera', exact: true })).toBeVisible();
  await expect(map).toContainText('$G \\times G \\to G$; edición persistida.');
  await progress('reloaded'); await screenshot('04-reloaded');
  await map.getByRole('button', { name: /Idea semilla · → implica/ }).click();
  await expect(map.getByRole('heading', { name: 'Idea semilla', exact: true })).toBeVisible();
  await map.getByRole('button', { name: 'Crear conectado', exact: true }).click();
  await map.getByLabel('Nombre', { exact: true }).fill('Subgrupo conectado');
  await map.getByLabel('Contenido (texto o LaTeX)', { exact: true }).fill('$H \\subseteq G$.');
  await map.getByRole('button', { name: 'Guardar', exact: true }).click();
  await expect(map.locator('canvas')).toHaveAttribute('data-edges', '2');
  await map.getByRole('button', { name: 'Plano', exact: true }).click();
  await expect(map.locator('canvas')).toHaveAttribute('data-nodes', '3');
  await progress('flat'); await screenshot('05-flat');
  await map.getByRole('button', { name: 'Esfera S²', exact: true }).click();
  await map.locator('canvas').focus(); await page.keyboard.press('ArrowLeft'); await page.keyboard.press('ArrowUp');
  await map.getByRole('button', { name: '+ Zoom', exact: true }).click();
  const box = await map.locator('canvas').boundingBox();
  await page.mouse.move(box.x + 80, box.y + 100); await page.mouse.down(); await page.mouse.move(box.x + 140, box.y + 130, {steps:4}); await page.mouse.up();
  const cdp = await context.newCDPSession(page);
  await cdp.send('Input.dispatchTouchEvent', {type:'touchStart',touchPoints:[{x:box.x+120,y:box.y+120}]});
  await cdp.send('Input.dispatchTouchEvent', {type:'touchMove',touchPoints:[{x:box.x+155,y:box.y+150}]});
  await cdp.send('Input.dispatchTouchEvent', {type:'touchEnd',touchPoints:[]}); await cdp.detach();
  const renderMs = Number(await map.locator('canvas').getAttribute('data-render-ms'));
  await progress('mouse-touch'); const collapse = page.getByRole('button', {name:'Collapse sidebar',exact:true}); if(await collapse.isVisible()) await collapse.click();
  await page.setViewportSize({ width: 420, height: 1000 });
  await expect(page.getByRole('button',{name:'Expand sidebar',exact:true})).toBeVisible();
  await progress('narrow'); await screenshot('06-narrow');
  // Existing note routing and return preserve exact selection and view context.
  await progress('open-note'); await map.getByRole('button', { name: 'Abrir nota / edición avanzada', exact: true }).click();
  await expect(page.getByRole('heading', { name: '✏️ Edit Mathematical Concept', exact: true })).toBeVisible();
  await page.setViewportSize({ width: 1440, height: 1100 });
  await navigate('🗺️ Grafo de conocimiento');
  await expect(map.getByRole('heading', { name: 'Subgrupo conectado', exact: true })).toBeVisible();
  if (errors.length) throw new Error(`Browser page errors: ${errors.join('; ')}`);
  const summary = { ok: true, flow: ['create', 'connect-existing', 'edit', 'reload', 'neighbor', 'create-connected', 'flat', 'keyboard', 'mouse', 'touch', 'narrow', 'open-existing-editor', 'return'], page_errors: errors, console_errors: consoleErrors, blocked_host_icon_requests: remote, graph_nodes: 3, graph_edges: 2, last_canvas_render_ms: renderMs, browser: await browser.version(), viewport: '1440x1100 / 420x1000', reduced_motion: true };
  await writeFile(`${evidence}/browser.json`, JSON.stringify(summary, null, 2) + '\n'); console.log(JSON.stringify(summary));
  }
} catch (error) { await page.screenshot({ path: `${evidence}/failure.png`, fullPage: true }); console.error(await page.locator('select').evaluateAll(nodes => nodes.map(n => ({label:n.parentElement?.textContent,options:[...n.options].map(o=>({value:o.value,text:o.textContent}))})))); throw error; } finally { await browser.close(); }

});
