// Credentials arrive only on stdin; stdout is sanitized machine evidence.
import { chromium } from "playwright";
import { randomBytes } from "node:crypto";
let input = "";
for await (const chunk of process.stdin) input += chunk;
const checks = {};
let browser;
function check(name, condition) { checks[name] = Boolean(condition); if (!condition) throw new Error("Live browser check failed"); }
function noPrivateKeys(data) { const forbidden = new Set(["no_ktp", "rekening", "npwp", "nama_rekening", "handphone", "email", "agama", "alamat_jakarta", "alamat_daerah"]); if (!data || typeof data !== "object") return true; return Object.entries(data).every(([key, value]) => !forbidden.has(key) && noPrivateKeys(value)); }
try {
  const config = JSON.parse(input);
  input = "";
  const origin = new URL(config.baseURL);
  if (origin.protocol !== "https:" || !/^[A-Za-z0-9+/]+={0,2}$/.test(config.spki || "")) throw new Error("HTTPS origin and explicit SPKI pin required");
  browser = await chromium.launch({ args: [`--ignore-certificate-errors-spki-list=${config.spki}`] });
  const context = await browser.newContext({ baseURL: origin.origin });
  const page = await context.newPage();
  let otherId, knownId, sourceName, sourceKtp, operatorListName;
  async function csrf() { return (await context.cookies(origin.origin)).find(c => c.name === "dpr_csrf")?.value || ""; }
  async function login(role) {
    await context.clearCookies();
    const account = config.accounts[role];
    const response = await page.goto("/login");
    check(`https_page_${role}`, response?.status() === 200);
    const csp = response.headers()["content-security-policy"] || "";
    check(`strict_csp_${role}`, csp.includes("'nonce-") && csp.includes("frame-ancestors 'none'") && !csp.includes("unsafe-inline") && !csp.includes("unsafe-eval"));
    await page.locator("#username").fill(account.username);
    await page.locator("#password").fill(account.password);
    await page.getByRole("button", { name: "Masuk ke aplikasi", exact: true }).click();
    await page.waitForURL(url => ["/anggota", "/analytics", "/audit"].includes(url.pathname), { timeout: 20000 });
    const me = await page.request.get("/api/auth/me");
    check(`login_${role}`, me.status() === 200 && (await me.json()).role === role);
    const session = (await context.cookies(origin.origin)).find(c => c.name === "dpr_session");
    check(`secure_cookie_${role}`, session?.httpOnly && session?.secure && session?.sameSite === "Strict");
    check(`empty_browser_storage_${role}`, await page.evaluate(() => localStorage.length === 0 && sessionStorage.length === 0));
  }
  await login("privileged_officer");
  const initialList = await (await page.request.get("/api/anggota?page=1")).json();
  check("privileged_list_envelope", initialList.page_size === 50 && initialList.items.length >= 2);
  knownId = initialList.items[0].anggota_id;
  otherId = initialList.items[1].anggota_id;
  const original = await (await page.request.get(`/api/anggota/${encodeURIComponent(knownId)}`)).json();
  sourceName = original.nama; sourceKtp = original.no_ktp;
  check("privileged_excludes_finance", !["rekening", "npwp", "nama_rekening", "kode_bank"].some(key => key in original));
  const replacement = `browser-${randomBytes(5).toString("hex")}@example.test`;
  try {
    await page.goto(`/anggota/${encodeURIComponent(knownId)}`);
    await page.getByRole("button", { name: "Perbarui kontak", exact: true }).click();
    await page.getByLabel("Email", { exact: true }).fill(replacement);
    await page.getByRole("button", { name: "Simpan perubahan", exact: true }).click();
    await page.getByRole("status").filter({ hasText: "berhasil diperbarui" }).waitFor();
    const updated = await page.request.get(`/api/anggota/${encodeURIComponent(knownId)}`);
    check("https_contact_patch", updated.status() === 200 && (await updated.json()).email === replacement);
  } finally {
    const restored = await page.request.patch(`/api/anggota/${encodeURIComponent(knownId)}/kontak`, { headers: { "X-CSRF-Token": await csrf() }, data: { email: original.email ?? null } });
    check("contact_restored", restored.status() === 200);
  }
  await page.goto("/pencarian");
  await page.getByLabel("Nilai pencarian", { exact: true }).fill(sourceKtp);
  await page.getByRole("button", { name: "Cari anggota", exact: true }).click();
  await page.locator("tbody tr").first().waitFor();
  check("https_exact_lookup", new URL(page.url()).search === "" && (await page.getByLabel("Nilai pencarian", { exact: true }).inputValue()) === "");

  await login("operator");
  const operatorListResponse = await page.request.get("/api/anggota?page=1");
  const operatorList = await operatorListResponse.json();
  operatorListName = operatorList.items.find(row => row.anggota_id === knownId)?.nama;
  check("operator_name_masked_in_json", Boolean(operatorListName) && operatorListName !== sourceName);
  check("list_only_allowed_fields", operatorList.items.every(row => Object.keys(row).every(key => ["anggota_id", "nama"].includes(key))));
  check("api_cache_headers", operatorListResponse.headers()["cache-control"]?.includes("no-store") && operatorListResponse.headers()["x-content-type-options"] === "nosniff");
  const operatorDetail = await (await page.request.get(`/api/anggota/${encodeURIComponent(knownId)}`)).json();
  check("operator_no_finance_or_religion", !["rekening", "npwp", "agama"].some(key => key in operatorDetail));
  check("operator_ktp_masked", typeof operatorDetail.no_ktp === "string" && operatorDetail.no_ktp !== sourceKtp);

  await login("finance_officer");
  const finance = await (await page.request.get(`/api/anggota/${encodeURIComponent(knownId)}`)).json();
  check("finance_fields_present", "rekening" in finance && "npwp" in finance && !("agama" in finance));
  await page.goto(`/anggota/${encodeURIComponent(knownId)}`);
  await page.getByRole("heading", { level: 1 }).waitFor();
  check("finance_no_contact_editor", await page.getByRole("button", { name: "Perbarui kontak" }).count() === 0);

  await login("anggota");
  const ownList = await (await page.request.get("/api/anggota?page=1")).json();
  check("anggota_own_record_only", ownList.total === 1 && ownList.items.length === 1);
  const forbiddenId = ownList.items[0].anggota_id === otherId ? knownId : otherId;
  const denied = await page.request.get(`/api/anggota/${encodeURIComponent(forbiddenId)}`);
  check("anggota_idor_denied", [403, 404].includes(denied.status()));

  await login("analyst");
  const analytics = await page.request.get("/api/analytics/summary");
  check("analyst_aggregate_only", analytics.status() === 200 && noPrivateKeys(await analytics.json()));
  check("analyst_detail_denied", [403, 404].includes((await page.request.get(`/api/anggota/${encodeURIComponent(knownId)}`)).status()));

  await login("auditor");
  const audit = await page.request.get("/api/audit?page=1");
  check("auditor_metadata_only", audit.status() === 200 && noPrivateKeys(await audit.json()));
  check("auditor_detail_denied", [403, 404].includes((await page.request.get(`/api/anggota/${encodeURIComponent(knownId)}`)).status()));
  await page.getByRole("button", { name: "Keluar", exact: true }).click();
  await page.waitForURL("**/login");
  check("logout_revokes_session", (await page.request.get("/api/auth/me")).status() === 401);
  await context.close();
  console.log(JSON.stringify({ status: "PASSED", checks }));
} catch (error) {
  console.log(JSON.stringify({ status: "FAILED", checks, error_type: error?.constructor?.name || "Error" }));
  process.exitCode = 1;
} finally { if (browser) await browser.close(); }
