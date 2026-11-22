// Adapted after generating Streamlit's official cookiecutter/v2 Pure Typescript
// template. Share MathMongo's existing toolchain; preserve the ESM renderer ABI.
import { defineConfig } from "vite";
import { runtimeNotices } from "./scripts/runtime-notices.mjs";
export default defineConfig({
  base: "./",
  plugins: [runtimeNotices()],
  publicDir: false,
  build: {
    outDir: "../../mathmongo/advanced_reader/static/knowledge_map",
    emptyOutDir: true,
    lib: {
      entry: "src/knowledge-map/component.ts",
      formats: ["es"],
      fileName: "index-[hash]",
    },
  },
});
