import { createHash } from "node:crypto";
import {
  lstat,
  mkdir,
  readFile,
  readdir,
  rename,
  rm,
  writeFile,
} from "node:fs/promises";
import { dirname, extname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const PDFJS_VERSION = "6.1.200";
const PDFJS_ASSET_DIRECTORY = `pdfjs-${PDFJS_VERSION}`;
const VIRTUAL_HOME = "/home/web_user";
const SANITIZED_VIRTUAL_HOME = "/virtual/web_user";

const projectRoot = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const packageRoot = resolve(projectRoot, "node_modules/pdfjs-dist");
const generatedRoot = resolve(projectRoot, "generated");
const generatedPublicRoot = resolve(generatedRoot, "public");
const packageJson = JSON.parse(await readFile(resolve(packageRoot, "package.json"), "utf8"));

if (packageJson.version !== PDFJS_VERSION) {
  throw new Error(
    `The installed pdfjs-dist version must be exactly ${PDFJS_VERSION}; found ${String(packageJson.version)}.`,
  );
}

const assetPolicies = Object.freeze({
  cmaps: Object.freeze({
    expectedCount: 169,
    inventorySha256: "95e459bcb13faa8998861ebf9954a86ac2ec362342318cef04ad67d38bfcc4d7",
    excludedNames: Object.freeze([]),
    nameAllowed: (name) => name === "LICENSE" || /^[A-Za-z0-9-]+\.bcmap$/u.test(name),
  }),
  standard_fonts: Object.freeze({
    expectedCount: 16,
    inventorySha256: "73e5de7c412df8ddaa70bad216fd9dc53b2af875cdbd0f8ece6ede4743a5ac9b",
    excludedNames: Object.freeze([]),
    nameAllowed: (name) =>
      name === "LICENSE_FOXIT" ||
      name === "LICENSE_LIBERATION" ||
      /^(?:Foxit[A-Za-z]+\.pfb|LiberationSans(?:-[A-Za-z]+)?\.ttf)$/u.test(name),
  }),
  iccs: Object.freeze({
    expectedCount: 2,
    inventorySha256: "8fd90bf5a81a9b10ea806bc1a50d878dc063e1439026a335853579e1ab544d3d",
    excludedNames: Object.freeze([]),
    nameAllowed: (name) => name === "LICENSE" || name === "CGATS001Compat-v2-micro.icc",
  }),
  wasm: Object.freeze({
    expectedCount: 11,
    inventorySha256: "10c87199f10de4a521ef246d65adb3b011706c14e06f1de8ebb99b64dc4e85ed",
    excludedNames: Object.freeze(["quickjs-eval.js", "quickjs-eval.wasm"]),
    nameAllowed: (name) =>
      /^(?:LICENSE_(?:JBIG2|OPENJPEG|PDFJS_JBIG2|PDFJS_OPENJPEG|PDFJS_QCMS|QCMS)|jbig2\.wasm|jbig2_nowasm_fallback\.js|openjpeg\.wasm|openjpeg_nowasm_fallback\.js|qcms_bg\.wasm)$/u.test(
        name,
      ),
  }),
});

function inventorySha256(names) {
  return createHash("sha256").update(`${names.join("\n")}\n`).digest("hex");
}

function validateInventory(directoryName, names, { source }) {
  const policy = assetPolicies[directoryName];
  const excluded = new Set(policy.excludedNames);
  if (source) {
    for (const name of excluded) {
      if (!names.includes(name)) {
        throw new Error(`The reviewed pdfjs-dist ${directoryName} inventory is missing ${name}.`);
      }
    }
  } else if (names.some((name) => excluded.has(name))) {
    throw new Error(`The prepared PDF.js runtime must not contain QuickJS sandbox assets.`);
  }

  const selected = names.filter((name) => !excluded.has(name)).sort();
  if (selected.some((name) => !policy.nameAllowed(name))) {
    throw new Error(`The pdfjs-dist ${directoryName} inventory contains a non-allowlisted file.`);
  }
  if (
    selected.length !== policy.expectedCount ||
    inventorySha256(selected) !== policy.inventorySha256
  ) {
    throw new Error(
      `The pdfjs-dist ${directoryName} inventory does not match the reviewed ${PDFJS_VERSION} allowlist.`,
    );
  }
  return selected;
}

async function regularFileNames(directory) {
  const entries = await readdir(directory, { withFileTypes: true });
  if (entries.some((entry) => !entry.isFile())) {
    throw new Error(`The reviewed PDF.js asset directory contains a non-regular entry: ${directory}`);
  }
  return entries.map((entry) => entry.name);
}

function sanitizeRuntimeText(source, label) {
  const sanitized = source.replaceAll(VIRTUAL_HOME, SANITIZED_VIRTUAL_HOME);
  if (sanitized.toLowerCase().includes("/home/")) {
    throw new Error(`The prepared ${label} still contains a HOME-like path.`);
  }
  return sanitized;
}

function normalizeRedistributedLicense(source) {
  const normalized = source.replaceAll("\r\n", "\n").replace(/[\t ]+$/gmu, "");
  return `${normalized.replace(/\n+$/u, "")}\n`;
}

async function prepareAssetDirectory(directoryName, destinationRoot) {
  const sourceDirectory = resolve(packageRoot, directoryName);
  const sourceNames = await regularFileNames(sourceDirectory);
  const selectedNames = validateInventory(directoryName, sourceNames, { source: true });
  const destinationDirectory = join(destinationRoot, directoryName);
  await mkdir(destinationDirectory, { recursive: true });

  for (const name of selectedNames) {
    const sourcePath = join(sourceDirectory, name);
    const destinationPath = join(destinationDirectory, name);
    if (extname(name) === ".js") {
      const source = await readFile(sourcePath, "utf8");
      await writeFile(
        destinationPath,
        sanitizeRuntimeText(source, `${directoryName}/${name}`),
        "utf8",
      );
    } else if (name.startsWith("LICENSE")) {
      await writeFile(
        destinationPath,
        normalizeRedistributedLicense(await readFile(sourcePath, "utf8")),
        "utf8",
      );
    } else {
      await writeFile(destinationPath, await readFile(sourcePath));
    }
  }
}

async function validatePreparedPublic(directory) {
  const rootEntries = (await readdir(directory, { withFileTypes: true })).sort((left, right) =>
    left.name.localeCompare(right.name),
  );
  if (
    rootEntries.length !== 2 ||
    rootEntries[0].name !== "assets" ||
    !rootEntries[0].isDirectory() ||
    rootEntries[1].name !== "favicon.svg" ||
    !rootEntries[1].isFile()
  ) {
    throw new Error("The prepared public tree must contain only assets and favicon.svg.");
  }

  const assetsRoot = join(directory, "assets");
  const assetEntries = await readdir(assetsRoot, { withFileTypes: true });
  if (
    assetEntries.length !== 1 ||
    assetEntries[0].name !== PDFJS_ASSET_DIRECTORY ||
    !assetEntries[0].isDirectory()
  ) {
    throw new Error("The prepared public tree has an unexpected PDF.js asset root.");
  }

  const pdfJsRoot = join(assetsRoot, PDFJS_ASSET_DIRECTORY);
  const pdfJsEntries = (await readdir(pdfJsRoot, { withFileTypes: true })).sort((left, right) =>
    left.name.localeCompare(right.name),
  );
  const expectedDirectories = Object.keys(assetPolicies).sort();
  if (
    pdfJsEntries.length !== expectedDirectories.length ||
    pdfJsEntries.some(
      (entry, index) => entry.name !== expectedDirectories[index] || !entry.isDirectory(),
    )
  ) {
    throw new Error("The prepared PDF.js tree contains an unexpected asset directory.");
  }
  for (const directoryName of expectedDirectories) {
    const assetDirectory = join(pdfJsRoot, directoryName);
    const names = await regularFileNames(assetDirectory);
    validateInventory(directoryName, names, { source: false });
    for (const name of names.filter((value) => extname(value) === ".js")) {
      sanitizeRuntimeText(await readFile(join(assetDirectory, name), "utf8"), name);
    }
  }
}

async function pathExists(path) {
  try {
    await lstat(path);
    return true;
  } catch (error) {
    if (error?.code === "ENOENT") return false;
    throw error;
  }
}

await mkdir(generatedRoot, { recursive: true });

const workerSourcePath = resolve(packageRoot, "build/pdf.worker.min.mjs");
const workerDestination = resolve(generatedRoot, "pdf.worker.min.mjs");
const workerStaging = resolve(generatedRoot, `.pdf.worker.min.mjs.prepare-${process.pid}`);
const workerSource = await readFile(workerSourcePath, "utf8");
if (!workerSource.includes(VIRTUAL_HOME)) {
  throw new Error("The reviewed PDF.js virtual HOME marker changed unexpectedly.");
}
const preparedWorker = sanitizeRuntimeText(workerSource, "PDF.js worker");

const publicStaging = resolve(generatedRoot, `.public.prepare-${process.pid}`);
const publicBackup = resolve(generatedRoot, `.public.backup-${process.pid}`);
await rm(workerStaging, { force: true });
await rm(publicStaging, { recursive: true, force: true });
await rm(publicBackup, { recursive: true, force: true });

let previousPublicMoved = false;
let replacementPublicMoved = false;
try {
  await writeFile(workerStaging, preparedWorker, "utf8");
  await rename(workerStaging, workerDestination);

  await mkdir(join(publicStaging, "assets", PDFJS_ASSET_DIRECTORY), { recursive: true });
  const faviconSource = resolve(projectRoot, "public/favicon.svg");
  const faviconStat = await lstat(faviconSource);
  if (!faviconStat.isFile() || faviconStat.isSymbolicLink()) {
    throw new Error("The reviewed favicon must be a regular file.");
  }
  await writeFile(join(publicStaging, "favicon.svg"), await readFile(faviconSource));
  const pdfJsDestination = join(publicStaging, "assets", PDFJS_ASSET_DIRECTORY);
  for (const directoryName of Object.keys(assetPolicies)) {
    await prepareAssetDirectory(directoryName, pdfJsDestination);
  }
  await validatePreparedPublic(publicStaging);

  if (await pathExists(generatedPublicRoot)) {
    await rename(generatedPublicRoot, publicBackup);
    previousPublicMoved = true;
  }
  await rename(publicStaging, generatedPublicRoot);
  replacementPublicMoved = true;
  await validatePreparedPublic(generatedPublicRoot);
  if (previousPublicMoved) await rm(publicBackup, { recursive: true });
} catch (error) {
  if (replacementPublicMoved && (await pathExists(generatedPublicRoot))) {
    await rm(generatedPublicRoot, { recursive: true, force: true });
  }
  if (previousPublicMoved && (await pathExists(publicBackup))) {
    await rename(publicBackup, generatedPublicRoot);
  }
  throw error;
} finally {
  await rm(workerStaging, { force: true });
  await rm(publicStaging, { recursive: true, force: true });
  if ((await pathExists(generatedPublicRoot)) && (await pathExists(publicBackup))) {
    await rm(publicBackup, { recursive: true, force: true });
  }
}
