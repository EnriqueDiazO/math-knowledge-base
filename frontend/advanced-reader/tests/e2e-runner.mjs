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
const expectedPdfSize = Number(
  process.env.MATHMONGO_ADVANCED_READER_E2E_EXPECTED_PDF_SIZE ?? "0",
);
const workerPathPattern = /^\/assets\/pdf\.worker\.min-[A-Za-z0-9_-]{8,}\.mjs$/u;

if (
  baseUrl.protocol !== "http:" ||
  !["127.0.0.1", "localhost", "[::1]"].includes(baseUrl.hostname) ||
  baseUrl.username ||
  baseUrl.password ||
  !DOCUMENT_ID_PATTERN.test(documentId) ||
  !Number.isInteger(expectedPages) ||
  expectedPages < 0 ||
  !Number.isInteger(expectedPdfSize) ||
  expectedPdfSize < 0
) {
  process.stdout.write(`${JSON.stringify({ ok: false, error: "invalid_local_e2e_configuration" })}\n`);
  process.exit(2);
}

const readerUrl = new URL("/reader", baseUrl);
readerUrl.search = new URLSearchParams({ document_id: documentId }).toString();
const pdfPath = `/api/advanced-reader/documents/${documentId}/pdf`;

function mainCanvasSelector(pageNumber) {
  return `.page[data-page-number="${pageNumber}"] .canvasWrapper canvas`;
}

function thumbnailCanvasSelector(pageNumber) {
  return `.thumbnail-button[data-page-number="${pageNumber}"] canvas`;
}

async function goToPdfPage(page, pageInput, pageNumber) {
  await pageInput.fill(String(pageNumber));
  await pageInput.press("Enter");
  await page.waitForFunction(
    ({ selector, target }) => Number(document.querySelector(selector)?.value) === target,
    { selector: "#pdf-page-input", target: pageNumber },
  );
}

async function waitForPaintedCanvas(page, selector, label) {
  const canvas = page.locator(selector).first();
  try {
    await canvas.waitFor({ state: "attached", timeout: 20_000 });
    await canvas.evaluate((element) => element.scrollIntoView({ block: "center" }));
    const readStats = async () => {
      const handle = await page.waitForFunction(
        ({ canvasSelector }) => {
          const candidates = [...document.querySelectorAll(canvasSelector)].filter(
            (element) => element instanceof HTMLCanvasElement,
          );
          for (const [candidateIndex, candidate] of candidates.entries()) {
            const bounds = candidate.getBoundingClientRect();
            const style = getComputedStyle(candidate);
            if (
              candidate.hidden ||
              style.display === "none" ||
              style.visibility === "hidden" ||
              Number(style.opacity) === 0 ||
              !Number.isFinite(candidate.width) ||
              !Number.isFinite(candidate.height) ||
              candidate.width <= 0 ||
              candidate.height <= 0 ||
              !Number.isFinite(bounds.width) ||
              !Number.isFinite(bounds.height) ||
              bounds.width <= 0 ||
              bounds.height <= 0
            ) {
              continue;
            }

            const sampleWidth = Math.max(1, Math.min(256, candidate.width));
            const sampleHeight = Math.max(1, Math.min(256, candidate.height));
            const sample = document.createElement("canvas");
            sample.width = sampleWidth;
            sample.height = sampleHeight;
            const context = sample.getContext("2d", { alpha: true, willReadFrequently: true });
            if (context === null) continue;
            try {
              context.drawImage(candidate, 0, 0, sampleWidth, sampleHeight);
            } catch {
              continue;
            }
            const pixels = context.getImageData(0, 0, sampleWidth, sampleHeight).data;
            let opaquePixels = 0;
            let nonWhitePixels = 0;
            let darkPixels = 0;
            let luminanceTotal = 0;
            let luminanceSquaredTotal = 0;
            for (let index = 0; index < pixels.length; index += 4) {
              const alpha = pixels[index + 3];
              if (alpha < 240) continue;
              const red = pixels[index];
              const green = pixels[index + 1];
              const blue = pixels[index + 2];
              const luminance = 0.2126 * red + 0.7152 * green + 0.0722 * blue;
              opaquePixels += 1;
              luminanceTotal += luminance;
              luminanceSquaredTotal += luminance * luminance;
              if (red < 248 || green < 248 || blue < 248) nonWhitePixels += 1;
              if (luminance < 220) darkPixels += 1;
            }
            const sampledPixels = sampleWidth * sampleHeight;
            if (opaquePixels < Math.floor(sampledPixels * 0.5)) continue;
            const averageLuminance = luminanceTotal / opaquePixels;
            const luminanceVariance =
              luminanceSquaredTotal / opaquePixels - averageLuminance * averageLuminance;
            const minimumNonWhite = Math.max(12, Math.floor(sampledPixels * 0.0005));
            const minimumDark = Math.max(6, Math.floor(sampledPixels * 0.0002));
            if (
              nonWhitePixels < minimumNonWhite ||
              darkPixels < minimumDark ||
              !Number.isFinite(luminanceVariance) ||
              luminanceVariance < 0.5
            ) {
              continue;
            }
            return {
              canvas_count: candidates.length,
              canvas_index: candidateIndex,
              canvas_width: candidate.width,
              canvas_height: candidate.height,
              client_width: Math.round(bounds.width * 100) / 100,
              client_height: Math.round(bounds.height * 100) / 100,
              sampled_pixel_count: sampledPixels,
              opaque_pixel_count: opaquePixels,
              non_white_pixel_count: nonWhitePixels,
              dark_pixel_count: darkPixels,
              luminance_variance: Math.round(luminanceVariance * 100) / 100,
            };
          }
          return null;
        },
        { canvasSelector: selector },
        { polling: 100, timeout: 20_000 },
      );
      const stats = await handle.jsonValue();
      await handle.dispose();
      return stats;
    };

    await readStats();
    await page.waitForTimeout(300);
    return await readStats();
  } catch {
    throw new Error(`${label}_not_painted`);
  }
}

const summary = {
  ok: false,
  health: false,
  metadata: false,
  pdfRange: false,
  documentLoaded: false,
  pdfVisible: false,
  pageOnePainted: false,
  interiorPagePainted: false,
  thumbnailPainted: false,
  totalPages: 0,
  thumbnails: false,
  navigation: false,
  pageInput: false,
  bookLabel: false,
  zoom: false,
  actualSize: false,
  fitPage: false,
  fitWidth: false,
  rotate: false,
  search: false,
  selection: false,
  selectionPage: null,
  save: false,
  reloadRestored: false,
  rangeRequestCount: 0,
  range206Count: 0,
  workerRequestCount: 0,
  workerLocal: false,
  workerMime: false,
  workerVersioned: false,
  screenshotBytes: 0,
  pixelStats: {},
  remoteRequests: [],
  failedRequests: [],
  abortedRequests: [],
  consoleErrors: [],
  consoleWarnings: [],
  pageErrors: [],
};

let browser;
try {
  browser = await chromium.launch({ executablePath: chromePath, headless: true });
  const context = await browser.newContext({ serviceWorkers: "block" });
  const rangeRequests = [];
  const rangeResponses = [];
  const workerResponses = [];

  context.on("request", (request) => {
    const url = new URL(request.url());
    if (["http:", "https:"].includes(url.protocol) && url.origin !== baseUrl.origin) {
      summary.remoteRequests.push(url.origin);
    }
    if (
      url.pathname === pdfPath &&
      request.headers().range
    ) {
      rangeRequests.push(request.headers().range);
      summary.rangeRequestCount = rangeRequests.length;
    }
  });
  context.on("requestfailed", (request) => {
    const url = new URL(request.url());
    const reason = request.failure()?.errorText ?? "network failure";
    const entry = `NETWORK ${url.pathname} ${reason}`.slice(0, 300);
    if (reason === "net::ERR_ABORTED") summary.abortedRequests.push(entry);
    else summary.failedRequests.push(entry);
  });
  context.on("response", (response) => {
    const url = new URL(response.url());
    if (response.status() >= 400) {
      summary.failedRequests.push(`${response.status()} ${url.pathname}`);
    }
    if (
      url.pathname === pdfPath &&
      response.status() === 206
    ) {
      rangeResponses.push({
        acceptRanges: response.headers()["accept-ranges"] ?? "",
        contentRange: response.headers()["content-range"] ?? "",
      });
      summary.range206Count = rangeResponses.filter(
        ({ acceptRanges, contentRange }) =>
          acceptRanges.toLowerCase() === "bytes" && /^bytes \d+-\d+\/\d+$/u.test(contentRange),
      ).length;
    }
    if (workerPathPattern.test(url.pathname)) {
      workerResponses.push({
        origin: url.origin,
        path: url.pathname,
        status: response.status(),
        contentType: response.headers()["content-type"] ?? "",
      });
      summary.workerRequestCount = workerResponses.length;
      summary.workerLocal = workerResponses.every(({ origin }) => origin === baseUrl.origin);
      summary.workerMime = workerResponses.every(
        ({ status, contentType }) => status === 200 && /(?:java|ecma)script/iu.test(contentType),
      );
      summary.workerVersioned = workerResponses.every(({ path }) => workerPathPattern.test(path));
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

  const metadataResponse = await context.request.get(
    new URL(`/api/advanced-reader/documents/${documentId}`, baseUrl).toString(),
  );
  const metadataBody = metadataResponse.ok() ? await metadataResponse.json() : {};
  summary.metadata =
    metadataResponse.ok() &&
    metadataBody.document_id === documentId &&
    metadataBody.kind === "pdf" &&
    Number(metadataBody.version?.size_bytes) > 0 &&
    (expectedPdfSize === 0 || Number(metadataBody.version?.size_bytes) === expectedPdfSize);
  if (!summary.metadata) throw new Error("metadata_check_failed");

  const explicitRange = await context.request.get(new URL(pdfPath, baseUrl).toString(), {
    headers: { Range: "bytes=0-1023" },
  });
  const explicitRangeHeaders = explicitRange.headers();
  const explicitRangeBody = await explicitRange.body();
  const expectedRangeLength = expectedPdfSize > 0 ? Math.min(1024, expectedPdfSize) : 1024;
  summary.pdfRange =
    explicitRange.status() === 206 &&
    explicitRangeHeaders["accept-ranges"]?.toLowerCase() === "bytes" &&
    /^bytes 0-1023\/\d+$/u.test(explicitRangeHeaders["content-range"] ?? "") &&
    Boolean(explicitRangeHeaders.etag) &&
    explicitRangeBody.length === expectedRangeLength &&
    explicitRangeBody.subarray(0, 5).toString("ascii") === "%PDF-";
  if (!summary.pdfRange) throw new Error("explicit_pdf_range_check_failed");

  const page = await context.newPage();
  page.on("console", (message) => {
    if (message.type() === "error" || message.type() === "warning") {
      const location = message.location();
      const entry = `${message.text()} @ ${location.url}:${location.lineNumber}`.slice(0, 300);
      if (message.type() === "error") summary.consoleErrors.push(entry);
      else summary.consoleWarnings.push(entry);
    }
  });
  page.on("pageerror", (error) => summary.pageErrors.push(error.message.slice(0, 300)));

  await page.goto(readerUrl.toString(), { waitUntil: "domcontentloaded" });
  await page.locator('.reader-app[data-phase="ready"]').waitFor({ state: "visible" });
  summary.documentLoaded = true;

  const totalLabel = await page.locator('[aria-label^="Total de páginas:"]').getAttribute("aria-label");
  summary.totalPages = Number(totalLabel?.split(":").at(-1)?.trim() ?? "0");
  if (summary.totalPages < 2 || (expectedPages > 0 && summary.totalPages !== expectedPages)) {
    throw new Error("unexpected_page_count");
  }
  const pageInput = page.locator("#pdf-page-input");
  await goToPdfPage(page, pageInput, 1);
  summary.pixelStats.page_1 = await waitForPaintedCanvas(
    page,
    mainCanvasSelector(1),
    "page_1",
  );
  summary.pdfVisible = true;
  summary.pageOnePainted = true;

  await page.locator(".thumbnail-button").first().waitFor({ state: "visible" });
  summary.pixelStats.thumbnail_1 = await waitForPaintedCanvas(
    page,
    thumbnailCanvasSelector(1),
    "thumbnail_1",
  );
  summary.thumbnailPainted = true;
  summary.thumbnails =
    (await page.locator(".thumbnail-button").count()) === summary.totalPages;

  const screenshot = await page.screenshot({ type: "png" });
  summary.screenshotBytes = screenshot.byteLength;

  await page.getByLabel("Página siguiente").click();
  await page.waitForFunction(
    ({ selector }) => Number(document.querySelector(selector)?.value) === 2,
    { selector: "#pdf-page-input" },
  );
  await page.getByLabel("Página anterior").click();
  await page.waitForFunction(
    ({ selector }) => Number(document.querySelector(selector)?.value) === 1,
    { selector: "#pdf-page-input" },
  );
  summary.navigation = true;

  const targetPage = Math.min(Math.max(2, Math.floor(summary.totalPages / 2)), summary.totalPages);
  await goToPdfPage(page, pageInput, targetPage);
  summary.pixelStats.interior = await waitForPaintedCanvas(
    page,
    mainCanvasSelector(targetPage),
    "interior_page",
  );
  summary.pageInput = true;
  summary.interiorPagePainted = true;
  const pageLabel = page.locator(".page-label");
  await pageLabel.filter({ hasText: `PDF page ${targetPage}` }).waitFor();
  const pageLabelText = await pageLabel.textContent();
  summary.bookLabel = expectedBookLabel
    ? pageLabelText?.includes(expectedBookLabel) === true
    : pageLabelText?.includes("PDF page") === true;

  const zoomOutput = page.getByLabel("Zoom actual");
  await page.getByRole("button", { name: "Tamaño real" }).click();
  await page.waitForFunction(
    () => document.querySelector('[aria-label="Zoom actual"]')?.textContent?.trim() === "100%",
  );
  summary.pixelStats.actual_size = await waitForPaintedCanvas(
    page,
    mainCanvasSelector(targetPage),
    "actual_size",
  );
  summary.actualSize = true;

  const zoomBefore = await zoomOutput.textContent();
  await page.getByLabel("Aumentar zoom").click();
  await page.waitForFunction(
    ({ before }) => document.querySelector('[aria-label="Zoom actual"]')?.textContent !== before,
    { before: zoomBefore },
  );
  summary.pixelStats.zoom = await waitForPaintedCanvas(
    page,
    mainCanvasSelector(targetPage),
    "zoom",
  );
  summary.zoom = true;

  await page.getByRole("button", { name: "Ajustar página" }).click();
  summary.pixelStats.fit_page = await waitForPaintedCanvas(
    page,
    mainCanvasSelector(targetPage),
    "fit_page",
  );
  summary.fitPage = true;

  await page.getByRole("button", { name: "Ajustar ancho" }).click();
  summary.pixelStats.fit_width = await waitForPaintedCanvas(
    page,
    mainCanvasSelector(targetPage),
    "fit_width",
  );
  summary.fitWidth = true;

  const rotationOutput = page.getByLabel("Rotación actual");
  const rotationBefore = await rotationOutput.textContent();
  await page.getByLabel("Rotar a la derecha").click();
  await page.waitForFunction(
    ({ before, target }) =>
      document.querySelector('[aria-label="Rotación actual"]')?.textContent !== before &&
      Number(document.querySelector("#pdf-page-input")?.value) === target,
    { before: rotationBefore, target: targetPage },
  );
  summary.pixelStats.rotation = await waitForPaintedCanvas(
    page,
    mainCanvasSelector(targetPage),
    "rotation",
  );
  summary.pixelStats.rotation_thumbnail = await waitForPaintedCanvas(
    page,
    thumbnailCanvasSelector(targetPage),
    "rotation_thumbnail",
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

  await goToPdfPage(page, pageInput, targetPage);
  await page.getByRole("button", { name: "Guardar posición" }).click();
  await page.getByText("Posición guardada.").waitFor({ state: "visible" });
  summary.save = true;

  await page.reload({ waitUntil: "domcontentloaded" });
  await page.locator('.reader-app[data-phase="ready"]').waitFor({ state: "visible" });
  await page.waitForFunction(
    ({ selector, target }) => Number(document.querySelector(selector)?.value) === target,
    { selector: "#pdf-page-input", target: targetPage },
  );
  summary.pixelStats.reload = await waitForPaintedCanvas(
    page,
    mainCanvasSelector(targetPage),
    "reload",
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
  summary.workerRequestCount = workerResponses.length;
  summary.workerLocal =
    workerResponses.length > 0 && workerResponses.every(({ origin }) => origin === baseUrl.origin);
  summary.workerMime =
    workerResponses.length > 0 &&
    workerResponses.every(
      ({ status, contentType }) => status === 200 && /(?:java|ecma)script/iu.test(contentType),
    );
  summary.workerVersioned =
    workerResponses.length > 0 &&
    workerResponses.every(({ path }) => workerPathPattern.test(path));
  if (!summary.workerLocal || !summary.workerMime || !summary.workerVersioned) {
    throw new Error("local_worker_validation_failed");
  }
  summary.remoteRequests = [...new Set(summary.remoteRequests)];
  summary.failedRequests = [...new Set(summary.failedRequests)];
  summary.abortedRequests = [...new Set(summary.abortedRequests)];
  if (summary.remoteRequests.length > 0) throw new Error("remote_request_observed");
  if (summary.failedRequests.length > 0) throw new Error("http_error_observed");
  if (summary.consoleErrors.length > 0) throw new Error("console_error_observed");
  if (summary.pageErrors.length > 0) throw new Error("page_error_observed");

  const requiredFlags = [
    "health",
    "metadata",
    "pdfRange",
    "documentLoaded",
    "pdfVisible",
    "pageOnePainted",
    "interiorPagePainted",
    "thumbnailPainted",
    "thumbnails",
    "navigation",
    "pageInput",
    "bookLabel",
    "zoom",
    "actualSize",
    "fitPage",
    "fitWidth",
    "rotate",
    "search",
    "selection",
    "save",
    "reloadRestored",
    "workerLocal",
    "workerMime",
    "workerVersioned",
  ];
  summary.ok =
    requiredFlags.every((key) => summary[key] === true) &&
    summary.selectionPage > 0 &&
    summary.totalPages > 0 &&
    summary.rangeRequestCount > 0 &&
    summary.range206Count > 0 &&
    summary.workerRequestCount > 0 &&
    summary.screenshotBytes > 0 &&
    summary.remoteRequests.length === 0 &&
    summary.failedRequests.length === 0 &&
    summary.consoleErrors.length === 0 &&
    summary.pageErrors.length === 0;
  await context.close();
} catch (error) {
  summary.error = error instanceof Error ? error.message.slice(0, 160) : "unknown_e2e_error";
} finally {
  await browser?.close();
}

process.stdout.write(`${JSON.stringify(summary)}\n`);
if (!summary.ok) process.exitCode = 1;
