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
const runMode = process.env.MATHMONGO_ADVANCED_READER_E2E_MODE ?? "full";
const expectedHighlightId =
  process.env.MATHMONGO_ADVANCED_READER_E2E_HIGHLIGHT_ID ?? "";
const expectedUnderlineId =
  process.env.MATHMONGO_ADVANCED_READER_E2E_UNDERLINE_ID ?? "";
const expectedHighlightPage = Number(
  process.env.MATHMONGO_ADVANCED_READER_E2E_HIGHLIGHT_PAGE ?? "0",
);
const expectedUnderlinePage = Number(
  process.env.MATHMONGO_ADVANCED_READER_E2E_UNDERLINE_PAGE ?? "0",
);
const underlineSearchText =
  process.env.MATHMONGO_ADVANCED_READER_E2E_UNDERLINE_TEXT ?? "gamma";
const maxVisualNormalizedDelta = 0.005;
const maxVisualPixelDelta = 3.25;
const maxVisualCoverageRatioDelta = 0.06;
const workerPathPattern = /^\/assets\/pdf\.worker\.min-[A-Za-z0-9_-]{8,}\.mjs$/u;
const annotationIdPattern = /^ann_[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/u;

if (
  baseUrl.protocol !== "http:" ||
  !["127.0.0.1", "localhost", "[::1]"].includes(baseUrl.hostname) ||
  baseUrl.username ||
  baseUrl.password ||
  !DOCUMENT_ID_PATTERN.test(documentId) ||
  !Number.isInteger(expectedPages) ||
  expectedPages < 0 ||
  !Number.isInteger(expectedPdfSize) ||
  expectedPdfSize < 0 ||
  !["full", "imported"].includes(runMode) ||
  (runMode === "imported" && (
    !annotationIdPattern.test(expectedHighlightId) ||
    !annotationIdPattern.test(expectedUnderlineId) ||
    !Number.isInteger(expectedHighlightPage) ||
    expectedHighlightPage < 1 ||
    !Number.isInteger(expectedUnderlinePage) ||
    expectedUnderlinePage < 1
  ))
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

function annotationMarkSelector(annotationId) {
  return `.visual-annotation-mark[data-annotation-id="${annotationId}"]`;
}

function annotationCard(page, annotationId) {
  return page.locator(`.visual-card[data-annotation-id="${annotationId}"]`);
}

async function selectRealText(page, pageInput, pdfPage, textHint) {
  await goToPdfPage(page, pageInput, pdfPage);
  await waitForPaintedCanvas(page, mainCanvasSelector(pdfPage), `selection_page_${pdfPage}`);
  const textLayer = page.locator(`.page[data-page-number="${pdfPage}"] .textLayer`);
  const preferred = textLayer.locator("span").filter({ hasText: textHint }).first();
  const fallback = textLayer.locator("span").filter({ hasText: /\S/u }).first();
  const selectable = (await preferred.count()) > 0 ? preferred : fallback;
  await selectable.waitFor({ state: "visible" });
  const selectedText = await selectable.evaluate((element) => {
    const range = document.createRange();
    range.selectNodeContents(element);
    const selection = window.getSelection();
    selection?.removeAllRanges();
    selection?.addRange(range);
    element.dispatchEvent(new PointerEvent("pointerup", { bubbles: true }));
    return selection?.toString().replace(/\s+/gu, " ").trim() ?? "";
  });
  await page.getByRole("heading", { name: "Selección válida de una página" }).waitFor();
  await page.getByRole("toolbar", { name: "Guardar selección como marca visual" }).waitFor();
  return { selectable, selectedText };
}

async function measureAnnotationGeometry(page, annotationId, pdfPage, quoteText) {
  const pageSelector = `.page[data-page-number="${pdfPage}"]`;
  const markSelector = `${pageSelector} ${annotationMarkSelector(annotationId)}`;
  await page.waitForFunction(
    ({ selector }) => [...document.querySelectorAll(selector)].some((element) => {
      const bounds = element.getBoundingClientRect();
      return bounds.width > 0 && bounds.height > 0;
    }),
    { selector: markSelector },
  );
  const textLayer = page.locator(`${pageSelector} .textLayer`);
  const preferred = textLayer.locator("span").filter({ hasText: quoteText }).first();
  const fallback = textLayer.locator("span").filter({ hasText: /\S/u }).first();
  const textSpan = (await preferred.count()) > 0 ? preferred : fallback;
  await textSpan.waitFor({ state: "visible" });
  const metric = await textSpan.evaluate((element, options) => {
    const pageElement = element.closest(options.pageSelector);
    if (!(pageElement instanceof HTMLElement)) return null;
    const pageBounds = pageElement.getBoundingClientRect();
    if (pageBounds.width <= 0 || pageBounds.height <= 0) return null;
    const normalize = (bounds) => ({
      x: (bounds.left - pageBounds.left) / pageBounds.width,
      y: (bounds.top - pageBounds.top) / pageBounds.height,
      width: bounds.width / pageBounds.width,
      height: bounds.height / pageBounds.height,
      left: bounds.left,
      top: bounds.top,
      right: bounds.right,
      bottom: bounds.bottom,
    });
    const range = document.createRange();
    range.selectNodeContents(element);
    const expected = [...range.getClientRects()]
      .filter((bounds) => bounds.width > 0 && bounds.height > 0)
      .map(normalize)
      .sort((left, right) => left.y - right.y || left.x - right.x);
    const observed = [...pageElement.querySelectorAll(options.markSelector)]
      .filter((mark) => mark instanceof HTMLElement)
      .map((mark) => normalize(mark.getBoundingClientRect()))
      .sort((left, right) => left.y - right.y || left.x - right.x);
    if (expected.length === 0 || observed.length === 0) {
      return {
        expectedRectCount: expected.length,
        observedRectCount: observed.length,
        maxNormalizedDelta: Number.POSITIVE_INFINITY,
        maxPixelDelta: Number.POSITIVE_INFINITY,
      };
    }
    const union = (rects) => {
      const left = Math.min(...rects.map((rect) => rect.left));
      const top = Math.min(...rects.map((rect) => rect.top));
      const right = Math.max(...rects.map((rect) => rect.right));
      const bottom = Math.max(...rects.map((rect) => rect.bottom));
      return normalize({ left, top, right, bottom, width: right - left, height: bottom - top });
    };
    const unionArea = (rects) => {
      const xs = [...new Set(rects.flatMap((rect) => [rect.x, rect.x + rect.width]))]
        .sort((left, right) => left - right);
      let area = 0;
      for (let index = 0; index < xs.length - 1; index += 1) {
        const left = xs[index];
        const right = xs[index + 1];
        if (right <= left) continue;
        const intervals = rects
          .filter((rect) => rect.x < right && rect.x + rect.width > left)
          .map((rect) => [rect.y, rect.y + rect.height])
          .sort((first, second) => first[0] - second[0]);
        let coveredHeight = 0;
        let start = null;
        let end = null;
        for (const [top, bottom] of intervals) {
          if (start === null || end === null) {
            start = top;
            end = bottom;
          } else if (top <= end) {
            end = Math.max(end, bottom);
          } else {
            coveredHeight += end - start;
            start = top;
            end = bottom;
          }
        }
        if (start !== null && end !== null) coveredHeight += end - start;
        area += (right - left) * coveredHeight;
      }
      return area;
    };
    const expectedArea = unionArea(expected);
    const observedArea = unionArea(observed);
    const coverageRatioDelta = Math.abs(expectedArea - observedArea) /
      Math.max(expectedArea, Number.EPSILON);
    const expectedComparison = expected.length === observed.length ? expected : [union(expected)];
    const observedComparison = expected.length === observed.length ? observed : [union(observed)];
    let maxNormalizedDelta = 0;
    let maxPixelDelta = 0;
    expectedComparison.forEach((target, index) => {
      const actual = observedComparison[index];
      for (const key of ["x", "y", "width", "height"]) {
        maxNormalizedDelta = Math.max(maxNormalizedDelta, Math.abs(target[key] - actual[key]));
      }
      for (const key of ["left", "top", "right", "bottom"]) {
        maxPixelDelta = Math.max(maxPixelDelta, Math.abs(target[key] - actual[key]));
      }
    });
    return {
      expectedRectCount: expected.length,
      observedRectCount: observed.length,
      maxNormalizedDelta: Math.round(maxNormalizedDelta * 1_000_000) / 1_000_000,
      maxPixelDelta: Math.round(maxPixelDelta * 1_000) / 1_000,
      coverageRatioDelta: Math.round(coverageRatioDelta * 1_000_000) / 1_000_000,
      comparison: expected.length === observed.length ? "rects" : "union",
      pageWidth: Math.round(pageBounds.width * 100) / 100,
      pageHeight: Math.round(pageBounds.height * 100) / 100,
      layerRotation: pageElement.querySelector(".visualAnnotationLayer")?.dataset.rotation ?? null,
      displayedRotation:
        document.querySelector('[aria-label="Rotación actual"]')?.textContent?.trim() ?? null,
    };
  }, { pageSelector, markSelector: annotationMarkSelector(annotationId) });
  if (
    metric === null ||
    metric.expectedRectCount < 1 ||
    metric.observedRectCount < 1 ||
    !Number.isFinite(metric.maxNormalizedDelta) ||
    !Number.isFinite(metric.maxPixelDelta) ||
    !Number.isFinite(metric.coverageRatioDelta) ||
    metric.maxNormalizedDelta > maxVisualNormalizedDelta ||
    metric.maxPixelDelta > maxVisualPixelDelta ||
    (metric.comparison === "union" &&
      metric.coverageRatioDelta > maxVisualCoverageRatioDelta)
  ) {
    summary.geometryFailure = { annotationId, pdfPage, metric };
    throw new Error(`visual_geometry_mismatch_${annotationId}`);
  }
  return metric;
}

async function createVisualAnnotation(page, pageInput, options) {
  const selection = await selectRealText(page, pageInput, options.pdfPage, options.textHint);
  const selectionToolbar = page.getByRole("toolbar", {
    name: "Guardar selección como marca visual",
  });
  await selectionToolbar.getByLabel("Color de la marca", { exact: true }).selectOption(options.color);
  await selectionToolbar
    .getByRole("button", { name: options.kind === "highlight" ? "Highlight" : "Underline" })
    .click();
  await page.getByRole("heading", { name: "Guardar explícitamente" }).waitFor();
  await page.getByLabel("Comentario de la marca").fill(options.body);
  await page.getByLabel("Tags de la marca").fill(options.tags);
  const responsePromise = page.waitForResponse((response) => {
    const url = new URL(response.url());
    return response.request().method() === "POST" &&
      url.pathname === `/api/advanced-reader/documents/${documentId}/visual-annotations`;
  });
  await page.getByRole("button", { name: "Guardar marca" }).click();
  const response = await responsePromise;
  if (!response.ok()) throw new Error(`visual_${options.kind}_save_failed`);
  const annotation = await response.json();
  if (
    !annotationIdPattern.test(annotation.annotation_id) ||
    annotation.kind !== options.kind ||
    annotation.status !== "active" ||
    annotation.pdf_page !== options.pdfPage ||
    annotation.visual_status !== "exact" ||
    annotation.quote_text !== selection.selectedText
  ) {
    throw new Error(`visual_${options.kind}_response_invalid`);
  }
  await page.locator(annotationMarkSelector(annotation.annotation_id)).first().waitFor({
    state: "attached",
  });
  const geometry = await measureAnnotationGeometry(
    page,
    annotation.annotation_id,
    options.pdfPage,
    annotation.quote_text,
  );
  return { annotation, geometry };
}

async function waitForVisualMutation(page, annotationId, method, suffix, action) {
  const responsePromise = page.waitForResponse((response) => {
    const url = new URL(response.url());
    return response.request().method() === method &&
      url.pathname === `/api/advanced-reader/visual-annotations/${annotationId}${suffix}`;
  });
  await action();
  const response = await responsePromise;
  if (!response.ok()) throw new Error(`visual_mutation_failed_${suffix || "edit"}`);
  return await response.json();
}

async function selectVisualFilter(page, label, value, expectedStatus) {
  const responsePromise = page.waitForResponse((response) => {
    const url = new URL(response.url());
    return response.request().method() === "GET" &&
      response.ok() &&
      url.pathname === `/api/advanced-reader/documents/${documentId}/visual-annotations` &&
      url.searchParams.get("status") === expectedStatus &&
      !url.searchParams.has("pdf_page");
  });
  await page.getByLabel(label).selectOption(value);
  const response = await responsePromise;
  return await response.json();
}

const summary = {
  ok: false,
  mode: runMode,
  health: false,
  metadata: false,
  visualCapabilities: false,
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
  highlightCreated: false,
  highlightAnnotationId: null,
  highlightPage: null,
  underlineCreated: false,
  underlineAnnotationId: null,
  underlinePage: null,
  visualOverlay: false,
  visualGeometry: {},
  visualGeometryTolerance: {
    maxNormalizedDelta: maxVisualNormalizedDelta,
    maxPixelDelta: maxVisualPixelDelta,
    maxCoverageRatioDelta: maxVisualCoverageRatioDelta,
  },
  geometryFailure: null,
  visualRehydrated: false,
  visualEdited: false,
  visualArchivedFiltered: false,
  visualReactivated: false,
  visualNavigation: false,
  lifecycleStage: null,
  importedRehydrated: false,
  importedGeometry: {},
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
  summary.visualCapabilities =
    metadataBody.capabilities?.persistent_highlights === true &&
    metadataBody.capabilities?.persistent_underlines === true &&
    metadataBody.capabilities?.visual_annotation_editing === true &&
    metadataBody.capabilities?.visual_annotation_archiving === true;
  if (!summary.visualCapabilities) throw new Error("visual_capabilities_not_initialized");

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

  if (runMode === "imported") {
    const totalLabel = await page
      .locator('[aria-label^="Total de páginas:"]')
      .getAttribute("aria-label");
    summary.totalPages = Number(totalLabel?.split(":").at(-1)?.trim() ?? "0");
    if (summary.totalPages < 2 || (expectedPages > 0 && summary.totalPages !== expectedPages)) {
      throw new Error("unexpected_imported_page_count");
    }
    const pageInput = page.locator("#pdf-page-input");
    const expectedAnnotations = [
      {
        annotationId: expectedHighlightId,
        pdfPage: expectedHighlightPage,
        kind: "highlight",
      },
      {
        annotationId: expectedUnderlineId,
        pdfPage: expectedUnderlinePage,
        kind: "underline",
      },
    ];
    for (const expected of expectedAnnotations) {
      await goToPdfPage(page, pageInput, expected.pdfPage);
      summary.pixelStats[`imported_${expected.kind}`] = await waitForPaintedCanvas(
        page,
        mainCanvasSelector(expected.pdfPage),
        `imported_${expected.kind}`,
      );
      const annotationResponse = await context.request.get(
        new URL(
          `/api/advanced-reader/visual-annotations/${expected.annotationId}`,
          baseUrl,
        ).toString(),
      );
      const annotation = annotationResponse.ok() ? await annotationResponse.json() : {};
      if (
        !annotationResponse.ok() ||
        annotation.annotation_id !== expected.annotationId ||
        annotation.document_id !== documentId ||
        annotation.kind !== expected.kind ||
        annotation.status !== "active" ||
        annotation.pdf_page !== expected.pdfPage ||
        annotation.visual_status !== "exact" ||
        typeof annotation.quote_text !== "string" ||
        !annotation.quote_text
      ) {
        throw new Error(`imported_${expected.kind}_invalid`);
      }
      summary.importedGeometry[expected.kind] = await measureAnnotationGeometry(
        page,
        expected.annotationId,
        expected.pdfPage,
        annotation.quote_text,
      );
    }
    await page.getByLabel("Alcance de anotaciones").selectOption("document");
    await annotationCard(page, expectedHighlightId).waitFor({ state: "visible" });
    await annotationCard(page, expectedUnderlineId).waitFor({ state: "visible" });
    summary.highlightAnnotationId = expectedHighlightId;
    summary.highlightPage = expectedHighlightPage;
    summary.underlineAnnotationId = expectedUnderlineId;
    summary.underlinePage = expectedUnderlinePage;
    summary.pdfVisible = true;
    summary.interiorPagePainted = true;
    summary.visualOverlay = true;
    summary.visualRehydrated = true;
    summary.importedRehydrated = true;
    const importedScreenshot = await page.screenshot({ type: "png" });
    summary.screenshotBytes = importedScreenshot.byteLength;
  } else {
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

  const highlightPage = 1;
  const highlightResult = await createVisualAnnotation(page, pageInput, {
    pdfPage: highlightPage,
    textHint: searchText,
    kind: "highlight",
    color: "yellow",
    body: "Comentario visual E2E inicial",
    tags: "e2e, s5b",
  });
  summary.selectionPage = highlightResult.annotation.pdf_page;
  summary.selection = summary.selectionPage === highlightPage;
  summary.highlightAnnotationId = highlightResult.annotation.annotation_id;
  summary.highlightPage = highlightPage;
  summary.highlightCreated = true;
  summary.visualOverlay = true;
  summary.visualGeometry.created = highlightResult.geometry;

  await page.getByRole("button", { name: "Tamaño real" }).click();
  await page.waitForFunction(
    () => document.querySelector('[aria-label="Zoom actual"]')?.textContent?.trim() === "100%",
  );
  await waitForPaintedCanvas(page, mainCanvasSelector(highlightPage), "visual_actual_size");
  summary.visualGeometry.actualSize = await measureAnnotationGeometry(
    page,
    highlightResult.annotation.annotation_id,
    highlightPage,
    highlightResult.annotation.quote_text,
  );

  const visualZoomBefore = await zoomOutput.textContent();
  await page.getByLabel("Aumentar zoom").click();
  await page.waitForFunction(
    ({ before }) => document.querySelector('[aria-label="Zoom actual"]')?.textContent !== before,
    { before: visualZoomBefore },
  );
  await waitForPaintedCanvas(page, mainCanvasSelector(highlightPage), "visual_zoom");
  summary.visualGeometry.zoom = await measureAnnotationGeometry(
    page,
    highlightResult.annotation.annotation_id,
    highlightPage,
    highlightResult.annotation.quote_text,
  );

  await page.getByRole("button", { name: "Ajustar página" }).click();
  await waitForPaintedCanvas(page, mainCanvasSelector(highlightPage), "visual_fit_page");
  summary.visualGeometry.fitPage = await measureAnnotationGeometry(
    page,
    highlightResult.annotation.annotation_id,
    highlightPage,
    highlightResult.annotation.quote_text,
  );

  await page.getByRole("button", { name: "Ajustar ancho" }).click();
  await waitForPaintedCanvas(page, mainCanvasSelector(highlightPage), "visual_fit_width");
  summary.visualGeometry.fitWidth = await measureAnnotationGeometry(
    page,
    highlightResult.annotation.annotation_id,
    highlightPage,
    highlightResult.annotation.quote_text,
  );

  const visualRotationBefore = await rotationOutput.textContent();
  await page.getByLabel("Rotar a la derecha").click();
  await page.waitForFunction(
    ({ before, target }) =>
      document.querySelector('[aria-label="Rotación actual"]')?.textContent !== before &&
      Number(document.querySelector("#pdf-page-input")?.value) === target,
    { before: visualRotationBefore, target: highlightPage },
  );
  await waitForPaintedCanvas(page, mainCanvasSelector(highlightPage), "visual_rotation");
  summary.visualGeometry.rotation = await measureAnnotationGeometry(
    page,
    highlightResult.annotation.annotation_id,
    highlightPage,
    highlightResult.annotation.quote_text,
  );

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
  await goToPdfPage(page, pageInput, highlightPage);
  await waitForPaintedCanvas(page, mainCanvasSelector(highlightPage), "reload_highlight");
  summary.visualGeometry.reloadHighlight = await measureAnnotationGeometry(
    page,
    highlightResult.annotation.annotation_id,
    highlightPage,
    highlightResult.annotation.quote_text,
  );

  const underlinePage = targetPage < summary.totalPages ? targetPage + 1 : 1;
  const underlineResult = await createVisualAnnotation(page, pageInput, {
    pdfPage: underlinePage,
    textHint: underlineSearchText,
    kind: "underline",
    color: "blue",
    body: "Underline visual E2E",
    tags: "e2e, underline",
  });
  summary.underlineAnnotationId = underlineResult.annotation.annotation_id;
  summary.underlinePage = underlinePage;
  summary.underlineCreated = true;
  summary.visualGeometry.underline = underlineResult.geometry;

  summary.lifecycleStage = "document_filter";
  await selectVisualFilter(page, "Alcance de anotaciones", "document", "active");
  const highlightCard = annotationCard(page, highlightResult.annotation.annotation_id);
  const underlineCard = annotationCard(page, underlineResult.annotation.annotation_id);
  await highlightCard.waitFor({ state: "visible" });
  await underlineCard.waitFor({ state: "visible" });

  await highlightCard.getByRole("button", { name: "Editar" }).click();
  await page
    .getByLabel(`Editar color ${highlightResult.annotation.annotation_id}`)
    .selectOption("green");
  await page
    .getByLabel(`Editar comentario ${highlightResult.annotation.annotation_id}`)
    .fill("Comentario visual E2E editado");
  await page
    .getByLabel(`Editar tags ${highlightResult.annotation.annotation_id}`)
    .fill("e2e, editado");
  const edited = await waitForVisualMutation(
    page,
    highlightResult.annotation.annotation_id,
    "PATCH",
    "",
    () => highlightCard.getByRole("button", { name: "Guardar cambios" }).click(),
  );
  if (
    edited.annotation_id !== highlightResult.annotation.annotation_id ||
    edited.kind !== "highlight" ||
    edited.color_label !== "green" ||
    edited.body !== "Comentario visual E2E editado" ||
    edited.tags?.join(",") !== "e2e,editado"
  ) {
    throw new Error("visual_edit_response_invalid");
  }
  await highlightCard.getByText("Comentario visual E2E editado").waitFor({ state: "visible" });
  summary.visualEdited = true;

  summary.lifecycleStage = "navigate_highlight";
  await highlightCard.getByRole("button", { name: "Ir a página" }).click();
  await page.waitForFunction(
    ({ target }) => Number(document.querySelector("#pdf-page-input")?.value) === target,
    { target: highlightPage },
  );
  await page
    .locator(`${annotationMarkSelector(highlightResult.annotation.annotation_id)}.is-targeted`)
    .first()
    .waitFor({ state: "attached" });

  summary.lifecycleStage = "archive_highlight";
  const archived = await waitForVisualMutation(
    page,
    highlightResult.annotation.annotation_id,
    "POST",
    "/archive",
    () => highlightCard.getByRole("button", { name: "Archivar" }).click(),
  );
  if (archived.status !== "archived") throw new Error("visual_archive_response_invalid");
  await highlightCard.waitFor({ state: "hidden" });
  await page
    .locator(annotationMarkSelector(highlightResult.annotation.annotation_id))
    .waitFor({ state: "detached" });
  summary.lifecycleStage = "archived_filter";
  const archivedList = await selectVisualFilter(
    page,
    "Estado de anotaciones",
    "archived",
    "archived",
  );
  if (!archivedList.items?.some((item) => item.annotation_id === highlightResult.annotation.annotation_id)) {
    throw new Error("archived_filter_missing_highlight");
  }
  await highlightCard.waitFor({ state: "visible" });
  await highlightCard.locator("header span").filter({ hasText: /· archived$/u })
    .waitFor({ state: "visible" });
  await page.getByLabel("Tipo de anotaciones").selectOption("highlight");
  await underlineCard.waitFor({ state: "hidden" });
  summary.visualArchivedFiltered = true;

  summary.lifecycleStage = "reactivate_highlight";
  const reactivated = await waitForVisualMutation(
    page,
    highlightResult.annotation.annotation_id,
    "POST",
    "/reactivate",
    () => highlightCard.getByRole("button", { name: "Reactivar" }).click(),
  );
  if (reactivated.status !== "active") throw new Error("visual_reactivate_response_invalid");
  await highlightCard.waitFor({ state: "hidden" });
  summary.lifecycleStage = "active_filter";
  const activeList = await selectVisualFilter(page, "Estado de anotaciones", "active", "active");
  if (
    !activeList.items?.some((item) => item.annotation_id === highlightResult.annotation.annotation_id)
  ) {
    throw new Error("active_filter_missing_highlight");
  }
  await highlightCard.waitFor({ state: "visible" });
  await page.getByLabel("Tipo de anotaciones").selectOption("all");
  await underlineCard.waitFor({ state: "visible" });
  await page
    .locator(annotationMarkSelector(highlightResult.annotation.annotation_id))
    .first()
    .waitFor({ state: "attached" });
  summary.visualReactivated = true;

  summary.lifecycleStage = "navigate_underline";
  await underlineCard.getByRole("button", { name: "Ir a página" }).click();
  await page.waitForFunction(
    ({ target }) => Number(document.querySelector("#pdf-page-input")?.value) === target,
    { target: underlinePage },
  );
  await page
    .locator(`${annotationMarkSelector(underlineResult.annotation.annotation_id)}.is-targeted`)
    .first()
    .waitFor({ state: "attached" });
  summary.visualNavigation = true;

  summary.lifecycleStage = "final_reload";
  await page.reload({ waitUntil: "domcontentloaded" });
  await page.locator('.reader-app[data-phase="ready"]').waitFor({ state: "visible" });
  await page.waitForFunction(
    ({ target }) => Number(document.querySelector("#pdf-page-input")?.value) === target,
    { target: targetPage },
  );
  await goToPdfPage(page, pageInput, highlightPage);
  await waitForPaintedCanvas(page, mainCanvasSelector(highlightPage), "final_visual_reload");
  summary.visualGeometry.finalHighlight = await measureAnnotationGeometry(
    page,
    highlightResult.annotation.annotation_id,
    highlightPage,
    highlightResult.annotation.quote_text,
  );
  await goToPdfPage(page, pageInput, underlinePage);
  await waitForPaintedCanvas(page, mainCanvasSelector(underlinePage), "final_underline_reload");
  summary.visualGeometry.finalUnderline = await measureAnnotationGeometry(
    page,
    underlineResult.annotation.annotation_id,
    underlinePage,
    underlineResult.annotation.quote_text,
  );
  summary.visualRehydrated = true;
  summary.lifecycleStage = "complete";
  }

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
  if (summary.consoleWarnings.length > 0) throw new Error("console_warning_observed");
  if (summary.pageErrors.length > 0) throw new Error("page_error_observed");

  const commonFlags = [
    "health",
    "metadata",
    "visualCapabilities",
    "pdfRange",
    "documentLoaded",
    "pdfVisible",
    "interiorPagePainted",
    "visualOverlay",
    "visualRehydrated",
    "workerLocal",
    "workerMime",
    "workerVersioned",
  ];
  const fullFlags = [
    "pageOnePainted",
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
    "highlightCreated",
    "underlineCreated",
    "visualEdited",
    "visualArchivedFiltered",
    "visualReactivated",
    "visualNavigation",
  ];
  const requiredFlags = runMode === "full"
    ? [...commonFlags, ...fullFlags]
    : [...commonFlags, "importedRehydrated"];
  summary.ok =
    requiredFlags.every((key) => summary[key] === true) &&
    (runMode === "imported" || summary.selectionPage > 0) &&
    annotationIdPattern.test(summary.highlightAnnotationId ?? "") &&
    annotationIdPattern.test(summary.underlineAnnotationId ?? "") &&
    summary.totalPages > 0 &&
    summary.rangeRequestCount > 0 &&
    summary.range206Count > 0 &&
    summary.workerRequestCount > 0 &&
    summary.screenshotBytes > 0 &&
    summary.remoteRequests.length === 0 &&
    summary.failedRequests.length === 0 &&
    summary.consoleErrors.length === 0 &&
    summary.consoleWarnings.length === 0 &&
    summary.pageErrors.length === 0;
  await context.close();
} catch (error) {
  summary.error = error instanceof Error ? error.message.slice(0, 160) : "unknown_e2e_error";
} finally {
  await browser?.close();
}

process.stdout.write(`${JSON.stringify(summary)}\n`);
if (!summary.ok) process.exitCode = 1;
