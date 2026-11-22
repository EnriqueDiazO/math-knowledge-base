/// <reference types="node" />
import { mkdtempSync, mkdirSync, writeFileSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { afterEach, expect, it, vi } from "vitest";
import { runtimeNotices } from "../scripts/runtime-notices.mjs";
let root: string | undefined;
afterEach(() => {
  if (root) rmSync(root, { recursive: true, force: true });
});
it("ships installed runtime licenses, skips development/absent platform packages and does not spawn tools", () => {
  root = mkdtempSync(join(tmpdir(), "mathmongo-notices-"));
  const pkg = (name: string, meta: Record<string, string>) => {
    const directory = join(root!, "node_modules", name);
    mkdirSync(directory, { recursive: true });
    writeFileSync(
      join(directory, "package.json"),
      JSON.stringify({ name, version: "1.0.0", ...meta }),
    );
    return directory;
  };
  const runtime = pkg("runtime", { license: "MIT" });
  writeFileSync(
    join(runtime, "LICENSE.txt"),
    "Copyright actual owner  \nPermission granted\n\n",
  );
  mkdirSync(join(runtime, "NOTICE"));
  pkg("shared-reader", {});
  pkg("dev-only", {});
  writeFileSync(
    join(root, "package-lock.json"),
    JSON.stringify({
      packages: {
        "": {},
        "node_modules/runtime": {},
        "node_modules/shared-reader": { license: "BSD-3-Clause" },
        "node_modules/dev-only": { dev: true },
        "node_modules/absent-platform": { optional: true },
      },
    }),
  );
  const emitFile = vi.fn();
  runtimeNotices(root).generateBundle.call({ emitFile });
  expect(emitFile).toHaveBeenCalledTimes(1);
  const artifact = emitFile.mock.calls[0][0];
  expect(artifact.fileName).toBe("THIRD_PARTY_LICENSES.txt");
  expect(artifact.source).toContain("runtime 1.0.0 (MIT)");
  expect(artifact.source).toContain("Copyright actual owner\nPermission granted");
  expect(artifact.source.endsWith("\n\n")).toBe(false);
  expect(artifact.source).toContain("shared-reader 1.0.0 (BSD-3-Clause)");
  expect(artifact.source).not.toContain("dev-only");
  expect(artifact.source).not.toContain("absent-platform");
});
