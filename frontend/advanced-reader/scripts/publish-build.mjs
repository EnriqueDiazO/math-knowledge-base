import { cp, lstat, mkdir, readFile, readdir, rename, rm, writeFile } from "node:fs/promises";
import { dirname, extname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const projectRoot = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const repositoryRoot = resolve(projectRoot, "../..");
const source = resolve(projectRoot, "dist");
const destination = resolve(
  repositoryRoot,
  "mathmongo/advanced_reader/static/advanced_reader",
);
const pdfJsLicense = resolve(projectRoot, "node_modules/pdfjs-dist/LICENSE");
const reactLicense = resolve(projectRoot, "node_modules/react/LICENSE");
const reactDomLicense = resolve(projectRoot, "node_modules/react-dom/LICENSE");

if (!destination.startsWith(`${repositoryRoot}/mathmongo/advanced_reader/static/`)) {
  throw new Error("Refusing to publish outside the controlled Advanced Reader static root.");
}

await readFile(join(source, "index.html"), "utf8");
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
  const workers = assetEntries.filter(
    (entry) => entry.isFile() && /^pdf\.worker\.min-[A-Za-z0-9_-]{8,}\.mjs$/u.test(entry.name),
  );
  if (workers.length !== 1) {
    throw new Error("Published build must contain exactly one hashed PDF.js worker");
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
