import { defineConfig } from '@playwright/test';
import path from 'node:path';
export default defineConfig({
  testDir: '.',
  testMatch: 'knowledge-map-browser.mjs',
  workers: 1,
  retries: 0,
  timeout: 150000,
  outputDir: path.join(process.env.MATHMONGO_MAP_TEST_EVIDENCE, 'playwright-' + (process.env.MATHMONGO_MAP_TEST_MODE ?? 'flow')),
  reporter: 'line',
});
