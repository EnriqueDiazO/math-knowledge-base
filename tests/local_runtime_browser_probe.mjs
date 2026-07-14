import { createRequire } from "node:module";

const require = createRequire(
  new URL("../frontend/advanced-reader/package.json", import.meta.url),
);
const { chromium } = require("@playwright/test");

const documentIdPattern =
  /^doc_[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/u;
function parseUrl(value) {
  try {
    return new URL(value);
  } catch {
    return null;
  }
}

const readerBase = parseUrl(process.env.MATHMONGO_LOCAL_RUNTIME_READER_URL ?? "");
const streamlitBase = parseUrl(
  process.env.MATHMONGO_LOCAL_RUNTIME_STREAMLIT_URL ?? "",
);
const documentId = process.env.MATHMONGO_LOCAL_RUNTIME_DOCUMENT_ID ?? "";
const documentTitle = process.env.MATHMONGO_LOCAL_RUNTIME_DOCUMENT_TITLE ?? "";
const chromePath = process.env.MATHMONGO_CHROME_PATH ?? "/usr/bin/google-chrome";

function validLoopbackBase(url) {
  return (
    url instanceof URL &&
    url.protocol === "http:" &&
    ["127.0.0.1", "localhost", "[::1]"].includes(url.hostname) &&
    url.username === "" &&
    url.password === "" &&
    url.pathname === "/" &&
    url.search === "" &&
    url.hash === ""
  );
}

function safeError(error) {
  const message = error instanceof Error ? error.message : "unknown_browser_error";
  return message
    .replace(/mongodb(?:\+srv)?:\/\/\S+/giu, "<redacted MongoDB URI>")
    .replace(/\/(?:home|tmp)\/[^\s'"]+/gu, "<local path omitted>")
    .slice(0, 240);
}

if (
  !validLoopbackBase(readerBase) ||
  !validLoopbackBase(streamlitBase) ||
  !documentIdPattern.test(documentId) ||
  documentTitle.length < 1 ||
  documentTitle.length > 200
) {
  process.stdout.write(
    `${JSON.stringify({ ok: false, error: "invalid_browser_probe_configuration" })}\n`,
  );
  process.exit(2);
}

const readerUrl = new URL("/reader", readerBase);
readerUrl.search = new URLSearchParams({ document_id: documentId }).toString();
const pdfPath = `/api/advanced-reader/documents/${documentId}/pdf`;

async function waitForPaintedFirstPage(page) {
  const handle = await page.waitForFunction(
    () => {
      const canvas = document.querySelector(
        '.page[data-page-number="1"] .canvasWrapper canvas',
      );
      if (!(canvas instanceof HTMLCanvasElement)) return null;
      const bounds = canvas.getBoundingClientRect();
      if (
        canvas.width < 1 ||
        canvas.height < 1 ||
        bounds.width < 1 ||
        bounds.height < 1
      ) {
        return null;
      }
      const sample = document.createElement("canvas");
      sample.width = Math.min(192, canvas.width);
      sample.height = Math.min(192, canvas.height);
      const context = sample.getContext("2d", {
        alpha: true,
        willReadFrequently: true,
      });
      if (context === null) return null;
      context.drawImage(canvas, 0, 0, sample.width, sample.height);
      const pixels = context.getImageData(0, 0, sample.width, sample.height).data;
      let opaque = 0;
      let nonWhite = 0;
      let dark = 0;
      for (let index = 0; index < pixels.length; index += 4) {
        if (pixels[index + 3] < 240) continue;
        opaque += 1;
        const red = pixels[index];
        const green = pixels[index + 1];
        const blue = pixels[index + 2];
        if (red < 248 || green < 248 || blue < 248) nonWhite += 1;
        if (0.2126 * red + 0.7152 * green + 0.0722 * blue < 220) dark += 1;
      }
      const total = sample.width * sample.height;
      if (
        opaque < total * 0.5 ||
        nonWhite < Math.max(12, total * 0.0005) ||
        dark < Math.max(6, total * 0.0002)
      ) {
        return null;
      }
      return {
        canvas_width: canvas.width,
        canvas_height: canvas.height,
        sampled_pixels: total,
        non_white_pixels: nonWhite,
        dark_pixels: dark,
      };
    },
    undefined,
    { polling: 100, timeout: 30_000 },
  );
  const value = await handle.jsonValue();
  await handle.dispose();
  return value;
}

async function selectStreamlitOption(page, label, optionText) {
  const selectbox = page
    .locator('[data-testid="stSidebar"] [data-testid="stSelectbox"]')
    .filter({ hasText: label })
    .first();
  await selectbox.waitFor({ state: "visible", timeout: 30_000 });
  await selectbox.getByRole("combobox").click();
  const option = page.getByRole("option").filter({ hasText: optionText }).first();
  await option.waitFor({ state: "visible", timeout: 10_000 });
  await option.click();
}

async function validateReader(context) {
  const page = await context.newPage();
  const pageErrors = [];
  const remoteOrigins = new Set();
  const pdfStatuses = [];
  const workerStatuses = [];
  page.on("pageerror", (error) => pageErrors.push(safeError(error)));
  page.on("request", (request) => {
    const url = new URL(request.url());
    if (["http:", "https:"].includes(url.protocol) && url.origin !== readerBase.origin) {
      remoteOrigins.add(url.origin);
    }
  });
  page.on("response", (response) => {
    const url = new URL(response.url());
    if (url.pathname === pdfPath) pdfStatuses.push(response.status());
    if (/^\/assets\/pdf\.worker\.min-[A-Za-z0-9_-]{8,}\.mjs$/u.test(url.pathname)) {
      workerStatuses.push(response.status());
    }
  });

  const navigation = await page.goto(readerUrl.href, {
    waitUntil: "domcontentloaded",
    timeout: 30_000,
  });
  if (navigation === null || navigation.status() !== 200) {
    throw new Error("advanced_reader_navigation_failed");
  }
  await page
    .locator('.reader-app[data-phase="ready"]')
    .waitFor({ state: "attached", timeout: 30_000 });
  const canvas = await waitForPaintedFirstPage(page);
  const textLayer = page.locator('.page[data-page-number="1"] .textLayer').first();
  await textLayer.waitFor({ state: "attached", timeout: 20_000 });
  const text = (await textLayer.textContent())?.replace(/\s+/gu, " ").trim() ?? "";
  const screenshot = await page.screenshot({ type: "png" });
  if (
    canvas === null ||
    !text.includes("Advanced Reader page 1") ||
    screenshot.byteLength < 1_000 ||
    pdfStatuses.every((status) => status !== 200 && status !== 206) ||
    workerStatuses.every((status) => status !== 200) ||
    remoteOrigins.size > 0 ||
    pageErrors.length > 0
  ) {
    throw new Error("advanced_reader_pdfjs_validation_failed");
  }
  await page.close();
  return {
    pdfjs_rendered: true,
    phase_ready: true,
    first_page_canvas_painted: true,
    first_page_text_layer: true,
    same_origin_pdf_response: true,
    local_worker_response: true,
    remote_request_count: remoteOrigins.size,
    page_error_count: pageErrors.length,
    screenshot_bytes: screenshot.byteLength,
    canvas,
  };
}

async function validateStreamlit(context) {
  const page = await context.newPage();
  await page.goto(streamlitBase.href, {
    waitUntil: "domcontentloaded",
    timeout: 30_000,
  });
  await page
    .locator('[data-testid="stAppViewContainer"]')
    .waitFor({ state: "visible", timeout: 30_000 });
  await selectStreamlitOption(page, "Navigation", "Reading Space");
  await page
    .getByRole("heading", { name: /Reading Space/u })
    .first()
    .waitFor({ state: "visible", timeout: 30_000 });

  const documentsTab = page.getByRole("tab", { name: "Documents", exact: true });
  await documentsTab.waitFor({ state: "visible", timeout: 20_000 });
  await documentsTab.click();
  const expander = page
    .locator('[data-testid="stExpander"]')
    .filter({ hasText: documentTitle })
    .first();
  await expander.waitFor({ state: "visible", timeout: 30_000 });
  await expander.locator("summary").click();
  const openButton = expander.getByRole("button", { name: "Open", exact: true });
  if (!(await openButton.isEnabled())) throw new Error("streamlit_document_open_disabled");
  await openButton.click();

  const workspaceTab = page.getByRole("tab", { name: "Workspace", exact: true });
  await workspaceTab.waitFor({ state: "visible", timeout: 30_000 });
  await workspaceTab.click();
  const ready = page.getByText("Lector avanzado listo.", { exact: true }).first();
  await ready.waitFor({ state: "visible", timeout: 30_000 });
  const link = page.getByRole("link", {
    name: "Abrir lector avanzado",
    exact: true,
  });
  await link.waitFor({ state: "visible", timeout: 20_000 });
  const href = await link.getAttribute("href");
  if (href === null) throw new Error("streamlit_reader_link_missing_href");
  const target = new URL(href, streamlitBase);
  const keys = [...target.searchParams.keys()];
  if (
    target.origin !== readerBase.origin ||
    target.pathname !== "/reader" ||
    keys.length !== 1 ||
    keys[0] !== "document_id" ||
    target.searchParams.get("document_id") !== documentId
  ) {
    throw new Error("streamlit_reader_link_not_document_only");
  }

  const popupPromise = context.waitForEvent("page", { timeout: 10_000 });
  await link.click();
  const popup = await popupPromise;
  await popup.waitForLoadState("domcontentloaded", { timeout: 20_000 });
  const opened = new URL(popup.url());
  if (opened.href !== target.href) throw new Error("streamlit_reader_link_did_not_open");
  await popup.close();
  await page.close();
  return {
    validated: true,
    reading_space_ready: true,
    document_opened: true,
    reader_status_ready: true,
    document_only_link: true,
    link_opened_reader: true,
  };
}

const summary = {
  ok: false,
  executed: true,
  engine: "playwright-google-chrome",
  reader: null,
  streamlit: null,
  error: null,
};
let browser;
try {
  browser = await chromium.launch({ executablePath: chromePath, headless: true });
  const context = await browser.newContext({
    viewport: { width: 1440, height: 1000 },
    serviceWorkers: "block",
  });
  summary.reader = await validateReader(context);
  summary.streamlit = await validateStreamlit(context);
  summary.ok = summary.reader.pdfjs_rendered && summary.streamlit.validated;
  await context.close();
} catch (error) {
  summary.error = safeError(error);
} finally {
  await browser?.close();
}

process.stdout.write(`${JSON.stringify(summary)}\n`);
if (!summary.ok) process.exitCode = 1;
