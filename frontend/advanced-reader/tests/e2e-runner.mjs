import { chromium } from "@playwright/test";

const DOCUMENT_ID_PATTERN =
  /^doc_[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/;
const baseUrl = new URL(
  process.env.MATHMONGO_ADVANCED_READER_E2E_URL ?? "http://127.0.0.1:8766",
);
const documentId = process.env.MATHMONGO_ADVANCED_READER_E2E_DOCUMENT_ID ?? "";
const chromePath = process.env.MATHMONGO_CHROME_PATH ?? "/usr/bin/google-chrome";
const searchText = process.env.MATHMONGO_ADVANCED_READER_E2E_SEARCH_TEXT ?? "MathMongo";
const expectedPages = Number(process.env.MATHMONGO_ADVANCED_READER_E2E_EXPECTED_PAGES ?? "0");
const expectedBookLabel = process.env.MATHMONGO_ADVANCED_READER_E2E_BOOK_LABEL ?? "";

if (
  baseUrl.protocol !== "http:" ||
  !["127.0.0.1", "localhost", "[::1]"].includes(baseUrl.hostname) ||
  baseUrl.username ||
  baseUrl.password ||
  !DOCUMENT_ID_PATTERN.test(documentId)
) {
  process.stdout.write(`${JSON.stringify({ ok: false, error: "invalid_local_e2e_configuration" })}\n`);
  process.exit(2);
}

const readerUrl = new URL("/reader", baseUrl);
readerUrl.search = new URLSearchParams({ document_id: documentId }).toString();
const summary = {
  ok: false,
  health: false,
  pdfVisible: false,
  totalPages: 0,
  thumbnails: false,
  navigation: false,
  pageInput: false,
  bookLabel: false,
  zoom: false,
  fitWidth: false,
  rotate: false,
  search: false,
  selection: false,
  selectionPage: null,
  save: false,
  reloadRestored: false,
  rangeRequestCount: 0,
  range206Count: 0,
  remoteRequests: [],
  failedRequests: [],
  consoleErrors: [],
  pageErrors: [],
};

let browser;
try {
  browser = await chromium.launch({ executablePath: chromePath, headless: true });
  const context = await browser.newContext({ serviceWorkers: "block" });
  const rangeRequests = [];
  const rangeResponses = [];

  context.on("request", (request) => {
    const url = new URL(request.url());
    if (["http:", "https:"].includes(url.protocol) && url.origin !== baseUrl.origin) {
      summary.remoteRequests.push(url.origin);
    }
    if (
      url.pathname === `/api/advanced-reader/documents/${documentId}/pdf` &&
      request.headers().range
    ) {
      rangeRequests.push(request.headers().range);
    }
  });
  context.on("response", (response) => {
    const url = new URL(response.url());
    if (response.status() >= 400) {
      summary.failedRequests.push(`${response.status()} ${url.pathname}`);
    }
    if (
      url.pathname === `/api/advanced-reader/documents/${documentId}/pdf` &&
      response.status() === 206
    ) {
      rangeResponses.push({
        acceptRanges: response.headers()["accept-ranges"] ?? "",
        contentRange: response.headers()["content-range"] ?? "",
      });
    }
  });

  const health = await context.request.get(
    new URL("/api/advanced-reader/health", baseUrl).toString(),
  );
  const healthBody = health.ok() ? await health.json() : {};
  summary.health =
    health.ok() &&
    healthBody.status === "ok" &&
    healthBody.service === "mathmongo-advanced-reader" &&
    healthBody.frontend_ready === true;
  if (!summary.health) throw new Error("health_check_failed");

  const page = await context.newPage();
  page.on("console", (message) => {
    if (message.type() === "error") {
      const location = message.location();
      summary.consoleErrors.push(
        `${message.text()} @ ${location.url}:${location.lineNumber}`.slice(0, 300),
      );
    }
  });
  page.on("pageerror", (error) => summary.pageErrors.push(error.message.slice(0, 300)));

  await page.goto(readerUrl.toString(), { waitUntil: "domcontentloaded" });
  await page.locator('.reader-app[data-phase="ready"]').waitFor({ state: "visible" });

  const totalLabel = await page.locator('[aria-label^="Total de páginas:"]').getAttribute("aria-label");
  summary.totalPages = Number(totalLabel?.split(":").at(-1)?.trim() ?? "0");
  if (summary.totalPages < 2 || (expectedPages > 0 && summary.totalPages !== expectedPages)) {
    throw new Error("unexpected_page_count");
  }
  const pageInput = page.locator("#pdf-page-input");
  let initialPage = Number(await pageInput.inputValue());
  await page
    .locator(`.page[data-page-number="${initialPage}"] canvas`)
    .first()
    .waitFor({ state: "visible" });
  summary.pdfVisible = true;

  await page.locator(".thumbnail-button").first().waitFor({ state: "visible" });
  summary.thumbnails = (await page.locator(".thumbnail-button").count()) === summary.totalPages;

  if (initialPage >= summary.totalPages) {
    await pageInput.fill("1");
    await pageInput.press("Enter");
    await page.waitForFunction(
      () =>
        document.querySelector("#pdf-page-input")?.value === "1" &&
        !document.querySelector('[aria-label="Página siguiente"]')?.disabled,
    );
    initialPage = 1;
  }
  await page.getByLabel("Página siguiente").click();
  await page.waitForFunction(
    ({ selector, initial }) => Number(document.querySelector(selector)?.value) === initial + 1,
    { selector: "#pdf-page-input", initial: initialPage },
  );
  summary.navigation = true;

  const targetPage = Math.min(Math.max(2, Math.floor(summary.totalPages / 2)), summary.totalPages);
  await pageInput.fill(String(targetPage));
  await pageInput.press("Enter");
  await page.waitForFunction(
    ({ selector, target }) => Number(document.querySelector(selector)?.value) === target,
    { selector: "#pdf-page-input", target: targetPage },
  );
  summary.pageInput = true;
  const pageLabel = page.locator(".page-label");
  await pageLabel.filter({ hasText: `PDF page ${targetPage}` }).waitFor();
  const pageLabelText = await pageLabel.textContent();
  summary.bookLabel = expectedBookLabel
    ? pageLabelText?.includes(expectedBookLabel) === true
    : pageLabelText?.includes("PDF page") === true;

  const zoomOutput = page.getByLabel("Zoom actual");
  const zoomBefore = await zoomOutput.textContent();
  await page.getByLabel("Aumentar zoom").click();
  await page.waitForFunction(
    ({ before }) => document.querySelector('[aria-label="Zoom actual"]')?.textContent !== before,
    { before: zoomBefore },
  );
  summary.zoom = true;
  const manualZoom = await zoomOutput.textContent();
  await page.getByRole("button", { name: "Ajustar página" }).click();
  await page.waitForFunction(
    ({ before }) => document.querySelector('[aria-label="Zoom actual"]')?.textContent !== before,
    { before: manualZoom },
  );
  const fitPageZoom = await zoomOutput.textContent();
  await page.getByRole("button", { name: "Ajustar ancho" }).click();
  await page.waitForFunction(
    ({ before }) => document.querySelector('[aria-label="Zoom actual"]')?.textContent !== before,
    { before: fitPageZoom },
  );
  summary.fitWidth = true;

  const rotationOutput = page.getByLabel("Rotación actual");
  const rotationBefore = await rotationOutput.textContent();
  await page.getByLabel("Rotar a la derecha").click();
  await page.waitForFunction(
    ({ before }) => document.querySelector('[aria-label="Rotación actual"]')?.textContent !== before,
    { before: rotationBefore },
  );
  summary.rotate = true;

  const search = page.getByLabel("Buscar en el PDF");
  await search.fill(searchText);
  await search.press("Enter");
  await page.waitForFunction(() => {
    const text = document.querySelector(".search-result")?.textContent?.trim() ?? "";
    return Boolean(text) && text !== "Buscando…";
  });
  const searchResult = (await page.locator(".search-result").textContent())?.trim() ?? "";
  summary.search = Boolean(searchResult) && searchResult !== "Sin resultados";
  if (!summary.search) throw new Error("search_text_not_found");

  const targetTextLayer = page.locator(
    `.page[data-page-number="${targetPage}"] .textLayer`,
  );
  const selectionSpan = targetTextLayer.locator("span").filter({ hasText: searchText }).first();
  const fallbackSpan = targetTextLayer.locator("span").filter({ hasText: /\S/u }).first();
  const selectable = (await selectionSpan.count()) > 0 ? selectionSpan : fallbackSpan;
  await selectable.waitFor({ state: "attached" });
  await selectable.evaluate((element) => {
    const range = document.createRange();
    range.selectNodeContents(element);
    const selection = window.getSelection();
    selection?.removeAllRanges();
    selection?.addRange(range);
    element.dispatchEvent(new PointerEvent("pointerup", { bubbles: true }));
  });
  await page.getByRole("heading", { name: "Selección válida de una página" }).waitFor();
  const selectionPageRow = page.getByRole("heading", { name: "Selección válida de una página" })
    .locator("xpath=following-sibling::dl[1]")
    .locator("div")
    .filter({ hasText: "PDF page" });
  summary.selectionPage = Number((await selectionPageRow.locator("dd").textContent()) ?? "0");
  summary.selection = summary.selectionPage === targetPage;

  await pageInput.fill(String(targetPage));
  await pageInput.press("Enter");
  await page.getByRole("button", { name: "Guardar posición" }).click();
  await page.getByText("Posición guardada.").waitFor({ state: "visible" });
  summary.save = true;

  await page.reload({ waitUntil: "domcontentloaded" });
  await page.locator('.reader-app[data-phase="ready"]').waitFor({ state: "visible" });
  await page.waitForFunction(
    ({ selector, target }) => Number(document.querySelector(selector)?.value) === target,
    { selector: "#pdf-page-input", target: targetPage },
  );
  summary.reloadRestored = true;

  const visibleText = await page.locator("body").innerText();
  if (/\/home\/|mongodb(?:\+srv)?:\/\/|file:\/\//iu.test(visibleText)) {
    throw new Error("sensitive_metadata_visible");
  }

  await page.waitForTimeout(250);
  summary.rangeRequestCount = rangeRequests.length;
  summary.range206Count = rangeResponses.filter(
    ({ acceptRanges, contentRange }) =>
      acceptRanges.toLowerCase() === "bytes" && /^bytes \d+-\d+\/\d+$/u.test(contentRange),
  ).length;
  if (summary.rangeRequestCount < 1 || summary.range206Count < 1) {
    throw new Error("pdf_range_not_observed");
  }
  if (summary.remoteRequests.length > 0) throw new Error("remote_request_observed");
  if (summary.failedRequests.length > 0) throw new Error("http_error_observed");
  if (summary.consoleErrors.length > 0) throw new Error("console_error_observed");
  if (summary.pageErrors.length > 0) throw new Error("page_error_observed");

  summary.ok = Object.entries(summary).every(([key, value]) => {
    if (["selectionPage", "totalPages", "rangeRequestCount", "range206Count"].includes(key)) {
      return typeof value === "number" && value > 0;
    }
    if (["remoteRequests", "failedRequests", "consoleErrors", "pageErrors"].includes(key)) {
      return Array.isArray(value) && value.length === 0;
    }
    return key === "ok" || value === true;
  });
  await context.close();
} catch (error) {
  summary.error = error instanceof Error ? error.message.slice(0, 160) : "unknown_e2e_error";
} finally {
  await browser?.close();
}

process.stdout.write(`${JSON.stringify(summary)}\n`);
if (!summary.ok) process.exitCode = 1;
