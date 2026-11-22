/** Ship the installed runtime dependency notices with the offline editor bundle. */
import fs from "node:fs";
import path from "node:path";
import { normalizeRedistributedLicense } from "./text-normalization.mjs";
const root = path.resolve(import.meta.dirname, "..");
export function runtimeNotices(directory = root, outputName = "THIRD_PARTY_LICENSES.txt") {
  return {
    name: "mathmongo-runtime-notices",
    generateBundle() {
      const lock = JSON.parse(
        fs.readFileSync(path.join(directory, "package-lock.json"), "utf8"),
      );
      const sections = [
        "MathMongo offline editor: installed runtime dependency notices.\nThis list may include runtime packages shared with the PDF reader.",
      ];
      for (const [relative, item] of Object.entries(lock.packages)) {
        if (!relative.startsWith("node_modules/") || item.dev) continue;
        const packageDirectory = path.join(directory, relative);
        if (!fs.existsSync(path.join(packageDirectory, "package.json")))
          continue;
        const manifest = JSON.parse(
          fs.readFileSync(path.join(packageDirectory, "package.json"), "utf8"),
        );
        sections.push(
          `\n=== ${manifest.name} ${manifest.version} (${manifest.license ?? item.license ?? "see notice"}) ===`,
        );
        const files = fs
          .readdirSync(packageDirectory)
          .filter((name) =>
            /^(?:licen[sc]e|copying|notice|ofl)(?:\.|$)/iu.test(name),
          );
        for (const name of files) {
          const file = path.join(packageDirectory, name);
          if (fs.statSync(file).isFile())
            sections.push(fs.readFileSync(file, "utf8"));
        }
      }
      this.emitFile({
        type: "asset",
        fileName: outputName,
        source: normalizeRedistributedLicense(sections.join("\n")),
      });
    },
  };
}
