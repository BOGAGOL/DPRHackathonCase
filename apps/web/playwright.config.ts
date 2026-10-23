import { defineConfig, devices } from "@playwright/test";
export default defineConfig({ testDir: "./e2e", fullyParallel: false, workers: 1, timeout: 45000,
  reporter: [["list"], ["json", { outputFile: "../../.local/browser-results.json" }]],
  use: { baseURL: "http://localhost:3000", trace: "off", screenshot: "off", video: "off" },
  projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"] } }]
});
