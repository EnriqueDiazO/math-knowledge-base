import { defineConfig } from "@playwright/test";
import path from "node:path";
export default defineConfig({
  testDir: ".",
  testMatch: "study-sphere-browser.mjs",
  workers: 1,
  retries: 0,
  timeout: 210000,
  outputDir: path.join(
    process.env.MATHMONGO_MAP_TEST_EVIDENCE,
    "playwright-study-" + process.env.MATHMONGO_STUDY_PHASE,
  ),
  reporter: "line",
});
