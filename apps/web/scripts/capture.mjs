// Local visual QA only. Mask member names before capturing shareable screenshots.
import { chromium } from "playwright";
import { readFileSync, mkdirSync } from "node:fs";
import path from "node:path";
const directory = path.resolve("../../.local");
mkdirSync(directory, { recursive: true });
const browser = await chromium.launch();
try {
  const page = await browser.newPage({ viewport: { width: 1440, height: 1080 } });
  await page.goto("http://localhost:3000/login");
  await page.screenshot({ path: path.join(directory, "login.png"), fullPage: true });
  const account = JSON.parse(readFileSync(path.join(directory, "demo-accounts.json"), "utf8")).find(a => a.role === "operator");
  await page.getByLabel("Username", { exact: true }).fill(account.username);
  await page.getByLabel("Password", { exact: true }).fill(account.password);
  await page.getByRole("button", { name: "Masuk ke aplikasi" }).click();
  await page.waitForURL("**/dashboard");
  await page.locator("tbody tr").first().waitFor();
  await page.locator(".member-cell strong").evaluateAll(elements => elements.forEach((e, i) => { e.textContent = `Anggota Sintetis ${i+1}`; }));
  await page.screenshot({ path: path.join(directory, "dashboard.png"), fullPage: true });
  console.log("Local visual QA screenshots saved with masked names.");
} finally { await browser.close(); }
