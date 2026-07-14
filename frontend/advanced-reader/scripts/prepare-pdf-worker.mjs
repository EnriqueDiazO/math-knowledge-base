import { mkdir, readFile, writeFile } from "node:fs/promises";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const projectRoot = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const packageRoot = resolve(projectRoot, "node_modules/pdfjs-dist");
const packageJson = JSON.parse(await readFile(resolve(packageRoot, "package.json"), "utf8"));
if (packageJson.version !== "6.1.200") {
  throw new Error("The installed pdfjs-dist version does not match the reviewed worker.");
}

const sourcePath = resolve(packageRoot, "build/pdf.worker.min.mjs");
const destination = resolve(projectRoot, "generated/pdf.worker.min.mjs");
const source = await readFile(sourcePath, "utf8");
const virtualHome = "/home/web_user";
if (!source.includes(virtualHome)) {
  throw new Error("The reviewed PDF.js virtual HOME marker changed unexpectedly.");
}
const sanitized = source.replaceAll(virtualHome, "/virtual/web_user");
if (sanitized.includes("/home/")) {
  throw new Error("The prepared PDF.js worker still contains a HOME-like path.");
}
await mkdir(dirname(destination), { recursive: true });
await writeFile(destination, sanitized, "utf8");
