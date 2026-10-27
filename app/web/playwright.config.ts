import { defineConfig, devices } from "@playwright/test";
export default defineConfig({
  testDir: "./tests", fullyParallel: false, workers: 1, timeout: 60000,
  outputDir: ".local/test-results",
  reporter: [["list"], ["json", { outputFile: ".local/ui-results.json" }]],
  use: { baseURL: "http://127.0.0.1:3310", trace: "off", screenshot: "off", video: "off" },
  projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"] } }],
  webServer: { command: "node node_modules/next/dist/bin/next start --hostname 127.0.0.1 --port 3310", url: "http://127.0.0.1:3310/login", reuseExistingServer: false, timeout: 60000 }
});
