import { createHash } from "node:crypto";
import { cp, lstat, mkdir, readFile, readdir, rename, rm, writeFile } from "node:fs/promises";
import { dirname, extname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const projectRoot = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const repositoryRoot = resolve(projectRoot, "../..");
const PDFJS_VERSION = "6.1.200";
const PDFJS_ASSET_DIRECTORY = `pdfjs-${PDFJS_VERSION}`;
const source = resolve(projectRoot, "dist");
const destination = resolve(
  repositoryRoot,
  "mathmongo/advanced_reader/static/advanced_reader",
);
const pdfJsLicense = resolve(projectRoot, "node_modules/pdfjs-dist/LICENSE");
const pdfJsPackageJson = resolve(projectRoot, "node_modules/pdfjs-dist/package.json");
const reactLicense = resolve(projectRoot, "node_modules/react/LICENSE");
const reactDomLicense = resolve(projectRoot, "node_modules/react-dom/LICENSE");

if (!destination.startsWith(`${repositoryRoot}/mathmongo/advanced_reader/static/`)) {
  throw new Error("Refusing to publish outside the controlled Advanced Reader static root.");
}

await readFile(join(source, "index.html"), "utf8");
const installedPdfJs = JSON.parse(await readFile(pdfJsPackageJson, "utf8"));
if (installedPdfJs.version !== PDFJS_VERSION) {
  throw new Error(`Publishing requires pdfjs-dist ${PDFJS_VERSION} exactly`);
}
const licenseText = await readFile(pdfJsLicense, "utf8");
const reactLicenseText = await readFile(reactLicense, "utf8");
const reactDomLicenseText = await readFile(reactDomLicense, "utf8");
const noticeDirectory = join(source, "third-party");
await mkdir(noticeDirectory, { recursive: true });
await writeFile(join(noticeDirectory, "pdfjs-LICENSE.txt"), licenseText, "utf8");
await writeFile(join(noticeDirectory, "react-LICENSE.txt"), reactLicenseText, "utf8");
await writeFile(join(noticeDirectory, "react-dom-LICENSE.txt"), reactDomLicenseText, "utf8");
await writeFile(
  join(noticeDirectory, "THIRD_PARTY_NOTICES.txt"),
  [
    "MathMongo Advanced Reader runtime dependencies",
    "",
    "pdfjs-dist 6.1.200 — Apache-2.0 — https://github.com/mozilla/pdf.js",
    "React 19.2.7 — MIT — https://github.com/facebook/react",
    "React DOM 19.2.7 — MIT — https://github.com/facebook/react",
    "",
    "The corresponding license texts are distributed in this directory.",
    "PDF.js runtime resources and their applicable upstream license files are",
    "distributed under /assets/pdfjs-6.1.200/.",
    "MathMongo replaces an embedded upstream virtual HOME marker with",
    "/virtual/web_user during packaging; decoder behavior is unchanged.",
  ].join("\n"),
  "utf8",
);

const forbiddenExtensions = new Set([".env", ".log", ".map", ".pdf"]);
const textualExtensions = new Set([".css", ".html", ".js", ".json", ".mjs", ".svg", ".txt"]);
const forbiddenRuntimeFragments = [
  "cdn.jsdelivr.net",
  "cdnjs.cloudflare.com",
  "unpkg.com",
  "fonts.googleapis.com",
  "google-analytics.com",
  "segment.io",
  "mongodb://",
  "file://",
  "/home/",
  "c:\\users\\",
  "super-secret",
];

const pdfJsAssetPolicies = Object.freeze({
  cmaps: Object.freeze({
    expectedCount: 169,
    inventorySha256: "95e459bcb13faa8998861ebf9954a86ac2ec362342318cef04ad67d38bfcc4d7",
    nameAllowed: (name) => name === "LICENSE" || /^[A-Za-z0-9-]+\.bcmap$/u.test(name),
  }),
  standard_fonts: Object.freeze({
    expectedCount: 16,
    inventorySha256: "73e5de7c412df8ddaa70bad216fd9dc53b2af875cdbd0f8ece6ede4743a5ac9b",
    nameAllowed: (name) =>
      name === "LICENSE_FOXIT" ||
      name === "LICENSE_LIBERATION" ||
      /^(?:Foxit[A-Za-z]+\.pfb|LiberationSans(?:-[A-Za-z]+)?\.ttf)$/u.test(name),
  }),
  iccs: Object.freeze({
    expectedCount: 2,
    inventorySha256: "8fd90bf5a81a9b10ea806bc1a50d878dc063e1439026a335853579e1ab544d3d",
    nameAllowed: (name) => name === "LICENSE" || name === "CGATS001Compat-v2-micro.icc",
  }),
  wasm: Object.freeze({
    expectedCount: 11,
    inventorySha256: "10c87199f10de4a521ef246d65adb3b011706c14e06f1de8ebb99b64dc4e85ed",
    nameAllowed: (name) =>
      /^(?:LICENSE_(?:JBIG2|OPENJPEG|PDFJS_JBIG2|PDFJS_OPENJPEG|PDFJS_QCMS|QCMS)|jbig2\.wasm|jbig2_nowasm_fallback\.js|openjpeg\.wasm|openjpeg_nowasm_fallback\.js|qcms_bg\.wasm)$/u.test(
        name,
      ),
  }),
});

function inventorySha256(names) {
  return createHash("sha256").update(`${names.join("\n")}\n`).digest("hex");
}

async function validatePdfJsAssetTree(assetsDirectory) {
  const pdfJsRoot = join(assetsDirectory, PDFJS_ASSET_DIRECTORY);
  const rootEntries = (await readdir(pdfJsRoot, { withFileTypes: true })).sort((left, right) =>
    left.name.localeCompare(right.name),
  );
  const expectedDirectories = Object.keys(pdfJsAssetPolicies).sort();
  if (
    rootEntries.length !== expectedDirectories.length ||
    rootEntries.some(
      (entry, index) => entry.name !== expectedDirectories[index] || !entry.isDirectory(),
    )
  ) {
    throw new Error("Published PDF.js assets contain an unexpected runtime directory");
  }

  for (const directoryName of expectedDirectories) {
    const entries = await readdir(join(pdfJsRoot, directoryName), { withFileTypes: true });
    if (entries.some((entry) => !entry.isFile())) {
      throw new Error(`Published PDF.js ${directoryName} assets must be regular files`);
    }
    const names = entries.map((entry) => entry.name).sort();
    const policy = pdfJsAssetPolicies[directoryName];
    if (
      names.some((name) => !policy.nameAllowed(name)) ||
      names.length !== policy.expectedCount ||
      inventorySha256(names) !== policy.inventorySha256
    ) {
      throw new Error(
        `Published PDF.js ${directoryName} assets do not match the ${PDFJS_VERSION} allowlist`,
      );
    }
  }
}

async function validateTree(directory, root = directory) {
  for (const entry of await readdir(directory, { withFileTypes: true })) {
    const path = join(directory, entry.name);
    if (entry.isDirectory()) {
      if (entry.name === "node_modules" || entry.name === ".vite") {
        throw new Error(`Forbidden build directory: ${entry.name}`);
      }
      await validateTree(path, root);
      continue;
    }
    if (!entry.isFile() || forbiddenExtensions.has(extname(entry.name))) {
      throw new Error(`Forbidden build artifact: ${entry.name}`);
    }
    if (
      !path.startsWith(`${join(root, "third-party")}/`) &&
      textualExtensions.has(extname(entry.name))
    ) {
      const content = (await readFile(path, "utf8")).toLowerCase();
      for (const fragment of forbiddenRuntimeFragments) {
        if (content.includes(fragment)) {
          throw new Error(`Forbidden runtime content in ${entry.name}: ${fragment}`);
        }
      }
      if (/\beval\s*\(/u.test(content) || /\bnew\s+function\s*\(/u.test(content)) {
        throw new Error(`Dynamic code execution found in ${entry.name}`);
      }
    }
  }
}

async function pathExists(path) {
  try {
    await lstat(path);
    return true;
  } catch (error) {
    if (error?.code === "ENOENT") {
      return false;
    }
    throw error;
  }
}

async function validateRuntimeShape(directory) {
  const indexPath = join(directory, "index.html");
  const html = await readFile(indexPath, "utf8");
  const references = [...html.matchAll(/(?:src|href)="(\/assets\/[A-Za-z0-9_.-]+)"/gu)].map(
    (match) => match[1],
  );
  if (!references.some((reference) => reference.endsWith(".js"))) {
    throw new Error("Published index does not reference a JavaScript entrypoint");
  }
  if (!references.some((reference) => reference.endsWith(".css"))) {
    throw new Error("Published index does not reference a stylesheet");
  }
  for (const reference of references) {
    const target = join(directory, reference.slice(1));
    if (!(await pathExists(target)) || !(await lstat(target)).isFile()) {
      throw new Error(`Published index references a missing asset: ${reference}`);
    }
  }

  const assets = join(directory, "assets");
  const assetEntries = await readdir(assets, { withFileTypes: true });
  const assetDirectories = assetEntries.filter((entry) => entry.isDirectory());
  if (
    assetDirectories.length !== 1 ||
    assetDirectories[0].name !== PDFJS_ASSET_DIRECTORY
  ) {
    throw new Error("Published build must contain exactly one versioned PDF.js asset directory");
  }
  await validatePdfJsAssetTree(assets);
  const workers = assetEntries.filter(
    (entry) => entry.isFile() && /^pdf\.worker\.min-[A-Za-z0-9_-]{8,}\.mjs$/u.test(entry.name),
  );
  if (workers.length !== 1) {
    throw new Error("Published build must contain exactly one hashed PDF.js worker");
  }
  if (!(await readFile(join(assets, workers[0].name), "utf8")).includes(PDFJS_VERSION)) {
    throw new Error(`Published PDF.js worker is not version ${PDFJS_VERSION}`);
  }
  for (const required of [
    "favicon.svg",
    "third-party/THIRD_PARTY_NOTICES.txt",
    "third-party/pdfjs-LICENSE.txt",
    "third-party/react-LICENSE.txt",
    "third-party/react-dom-LICENSE.txt",
  ]) {
    const target = join(directory, required);
    if (!(await pathExists(target)) || !(await lstat(target)).isFile()) {
      throw new Error(`Published build is missing ${required}`);
    }
  }

  for (const match of html.matchAll(/<script\b([^>]*)>([\s\S]*?)<\/script>/giu)) {
    if (!/\bsrc="\/assets\//u.test(match[1]) || match[2].trim()) {
      throw new Error("Published index contains an inline or non-local script");
    }
  }
}

await validateTree(source);
await validateRuntimeShape(source);

const staging = `${destination}.publish-${process.pid}`;
const backup = `${destination}.backup-${process.pid}`;
await mkdir(dirname(destination), { recursive: true });
await rm(staging, { recursive: true, force: true });
await rm(backup, { recursive: true, force: true });
await cp(source, staging, { recursive: true, errorOnExist: true, force: false });
await validateTree(staging);
await validateRuntimeShape(staging);

let previousMoved = false;
let replacementMoved = false;
try {
  if (await pathExists(destination)) {
    await rename(destination, backup);
    previousMoved = true;
  }
  await rename(staging, destination);
  replacementMoved = true;
  await validateTree(destination);
  await validateRuntimeShape(destination);
  if (previousMoved) {
    await rm(backup, { recursive: true });
  }
} catch (error) {
  if (replacementMoved && (await pathExists(destination))) {
    await rm(destination, { recursive: true, force: true });
  }
  if (previousMoved && (await pathExists(backup))) {
    await rename(backup, destination);
  }
  throw error;
} finally {
  await rm(staging, { recursive: true, force: true });
  if ((await pathExists(destination)) && (await pathExists(backup))) {
    await rm(backup, { recursive: true, force: true });
  }
}
