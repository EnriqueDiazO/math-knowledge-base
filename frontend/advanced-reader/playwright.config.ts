import { defineConfig } from "@playwright/test";

const baseURL = process.env.MATHMONGO_ADVANCED_READER_E2E_URL ?? "http://127.0.0.1:8766";
const executablePath = process.env.MATHMONGO_CHROME_PATH ?? "/usr/bin/google-chrome";

export default defineConfig({
  testDir: "./e2e",
  fullyParallel: false,
  workers: 1,
  retries: 0,
  forbidOnly: true,
  reporter: "list",
  use: {
    baseURL,
    browserName: "chromium",
    headless: true,
    serviceWorkers: "block",
    launchOptions: { executablePath },
  },
});
