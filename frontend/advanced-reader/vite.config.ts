import react from "@vitejs/plugin-react";
import type { Plugin } from "vite";
import { defineConfig } from "vitest/config";

function normalizeGeneratedSvgWhitespace(): Plugin {
  return {
    name: "mathmongo-normalize-generated-svg-whitespace",
    apply: "build",
    generateBundle(_options, bundle) {
      for (const output of Object.values(bundle)) {
        if (
          output.type === "asset" &&
          output.fileName.endsWith(".svg")
        ) {
          const source =
            typeof output.source === "string"
              ? output.source
              : new TextDecoder().decode(output.source);
          output.source = source.replace(/[\t ]+$/gmu, "");
        }
      }
    },
  };
}

export default defineConfig({
  plugins: [react(), normalizeGeneratedSvgWhitespace()],
  base: "/",
  publicDir: "generated/public",
  define: {
    process: "undefined",
  },
  server: {
    host: "127.0.0.1",
    port: 5173,
    strictPort: true,
    proxy: {
      "/api/advanced-reader": {
        target: "http://127.0.0.1:8766",
        changeOrigin: false,
      },
    },
  },
  build: {
    outDir: "dist",
    emptyOutDir: true,
    assetsDir: "assets",
    assetsInlineLimit: 0,
    chunkSizeWarningLimit: 1400,
    sourcemap: false,
    rollupOptions: {
      output: {
        entryFileNames: "assets/[name]-[hash].js",
        chunkFileNames: "assets/[name]-[hash].js",
        assetFileNames: "assets/[name]-[hash][extname]",
        manualChunks(id) {
          if (/\/node_modules\/(?:react|react-dom|scheduler)\//u.test(id)) {
            return "react-runtime";
          }
          if (id.includes("/node_modules/pdfjs-dist/")) {
            return "pdfjs-runtime";
          }
          return undefined;
        },
      },
    },
  },
  test: {
    environment: "jsdom",
    setupFiles: ["./tests/setup.ts"],
    css: false,
    clearMocks: true,
    restoreMocks: true,
  },
});
