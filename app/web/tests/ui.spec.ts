import { test, expect, type Page } from "@playwright/test";
import { randomBytes } from "node:crypto";
import { contentSecurityPolicy } from "../src/lib/csp";
import { canReadRecords, canEditContact, homeForRole } from "../src/lib/api";
import { forwardToBackend, upstreamUrl } from "../src/lib/backend-proxy";
type Role = "operator" | "privileged_officer" | "finance_officer" | "analyst" | "auditor" | "anggota";
const member = { anggota_id: "1", nama: "Anggota Uji Sintetis" };
const list = { items: [member], total: 1, page: 1, page_size: 50 };
test("API proxy verifies HTTPS configuration and withholds sensitive upstream error text", async () => {
  expect(() => upstreamUrl(["anggota", "search"], "", "http://127.0.0.1:8100")).toThrow();
  expect(() => upstreamUrl(["anggota", ".."], "", "https://127.0.0.1:8100")).toThrow();
  expect(() => upstreamUrl(["anggota"], "", `https://${randomBytes(6).toString("hex")}:${randomBytes(8).toString("hex")}@example.test`)).toThrow();
  const value = "synthetic-lookup@example.test";
  const response = await forwardToBackend(new Request(`https://localhost:3443/api/anggota/search?email=${value}`), ["anggota", "search"], async () => { throw new Error(`Upstream error for ${value}`); });
  expect(response.status).toBe(502);
  expect(await response.text()).not.toContain(value);
  expect(response.headers.get("cache-control")).toBe("no-store");
});

test("API proxy preserves session cookies and CSRF without accepting redirects", async () => {
  const cookie = randomBytes(32).toString("base64url"), csrf = randomBytes(32).toString("base64url");
  const response = await forwardToBackend(new Request("https://localhost:3443/api/auth/login", { method: "POST", headers: { "x-csrf-token": csrf, origin: "https://localhost:3443", "content-type": "application/json" }, body: "{}" }), ["auth", "login"], async (_url, options) => {
    expect(new Headers(options?.headers).get("x-csrf-token")).toBe(csrf);
    expect(options?.redirect).toBe("manual");
    return new Response("{}", { headers: { "set-cookie": `dpr_session=${cookie}; HttpOnly; Secure; SameSite=Strict; Path=/` } });
  });
  expect(response.headers.getSetCookie()[0]).toContain("HttpOnly; Secure; SameSite=Strict");
  const redirect = await forwardToBackend(new Request("https://localhost:3443/api/auth/me"), ["auth", "me"], async () => new Response(null, { status: 302, headers: { location: "https://untrusted.example.test" } }));
  expect(redirect.status).toBe(502);
});
test("navigation policy and nonce validation deny unsupported usage", () => {
  expect(() => contentSecurityPolicy("invalid'nonce")).toThrow();
  for (const role of ["operator", "privileged_officer", "finance_officer", "analyst", "auditor", "anggota"] as const) {
    expect(canReadRecords(role)).toBe(!["analyst", "auditor"].includes(role));
    expect(canEditContact(role)).toBe(["operator", "privileged_officer", "anggota"].includes(role));
    expect(homeForRole(role)).toBe(role === "analyst" ? "/analytics" : role === "auditor" ? "/audit" : "/anggota");
  }
});
async function mock(page: Page, role: Role, payload: Record<string, unknown> = {}) {
  await page.route("**/api/**", async route => {
    const request = route.request(), url = new URL(request.url()), endpoint = url.pathname.slice(4);
    let data: unknown = {};
    if (["/auth/me", "/auth/login"].includes(endpoint)) data = { id: "synthetic-user", username: "uji.browser", role };
    else if (["/auth/csrf", "/auth/logout"].includes(endpoint)) data = { message: "ok" };
    else if (endpoint === "/anggota" && request.method() === "POST") data = { ...member, ...request.postDataJSON() };
    else if (endpoint === "/anggota" || endpoint === "/anggota/search") data = list;
    else if (endpoint.endsWith("/kontak")) data = { ...member, ...request.postDataJSON() };
    else if (endpoint === "/anggota/1") data = { ...member, no_ktp: "00123456789012", email: "u••••@••••", handphone: "••••89", ...payload };
    else if (endpoint === "/analytics/summary") data = { total: null, groups: [{ dimension: "age_band", value: "40-49", count: 5 }] };
    else if (endpoint === "/audit") data = { total: 1, page: 1, page_size: 50, items: [{ id: 1, actor: "synthetic-user", role: "operator", action: "member.detail", anggota_id: "1", field_class: ["PII"], decision: "allowed", request_id: "synthetic-request", created_at: "2026-10-27T00:00:00Z" }] };
    await route.fulfill({ contentType: "application/json", headers: { "Cache-Control": "no-store" }, body: JSON.stringify(data) });
  });
}

test("strict CSP has a different nonce on each request and every inline script is nonced", async ({ page }) => {
  const first = await page.goto("/login");
  const header = first!.headers()["content-security-policy"];
  expect(header).not.toContain("unsafe-inline"); expect(header).not.toContain("unsafe-eval");
  expect(header).toContain("frame-ancestors 'none'"); expect(header).toContain("object-src 'none'");
  expect(first!.headers()["x-content-type-options"]).toBe("nosniff");
  expect(first!.headers()["referrer-policy"]).toBe("no-referrer");
  expect(first!.headers()["cache-control"]).toContain("no-store");
  const missing = await page.locator("script:not([src])").evaluateAll(elements => elements.filter(e => !(e as HTMLScriptElement).nonce).length);
  expect(missing).toBe(0);
  const second = await page.reload();
  expect(second!.headers()["content-security-policy"]).not.toBe(header);
});

test("login works under strict CSP without writing browser storage", async ({ page }) => {
  await mock(page, "operator");
  await page.goto("/login");
  await page.getByLabel("Username", { exact: true }).fill("uji.browser");
  await page.getByLabel("Password", { exact: true }).fill(randomBytes(24).toString("base64url"));
  await page.getByRole("button", { name: "Masuk ke aplikasi" }).click();
  await expect(page).toHaveURL(/\/anggota$/);
  await expect(page.locator("tbody tr")).toHaveCount(1);
  expect(await page.evaluate(() => ({ local: localStorage.length, session: sessionStorage.length }))).toEqual({ local: 0, session: 0 });
});

test("member profile escapes XSS and only PATCHes changed contact fields", async ({ page }) => {
  const xss = "<script>window.__dpr_xss_executed=true</script>";
  await mock(page, "operator", { nama: xss });
  await page.goto("/anggota/1");
  await expect(page.getByRole("heading", { level: 1 })).toHaveText(xss);
  expect(await page.evaluate(() => (window as unknown as Record<string, unknown>).__dpr_xss_executed)).toBeUndefined();
  expect(await page.locator("script").evaluateAll(elements => elements.some(e => e.textContent === "window.__dpr_xss_executed=true"))).toBe(false);
  await page.getByRole("button", { name: "Perbarui kontak" }).click();
  await expect(page.getByLabel("Email", { exact: true })).toHaveValue("");
  await page.getByLabel("Email", { exact: true }).fill("replacement@example.test");
  const request = page.waitForRequest(r => r.url().endsWith("/anggota/1/kontak") && r.method() === "PATCH");
  await page.getByRole("button", { name: "Simpan perubahan" }).click();
  expect((await request).postDataJSON()).toEqual({ email: "replacement@example.test" });
  await expect(page.getByRole("status")).toContainText("berhasil diperbarui");
});

test("exact search uses API fetch without adding identifiers to the page URL", async ({ page }) => {
  await mock(page, "privileged_officer");
  await page.goto("/pencarian");
  await page.getByLabel("Cari berdasarkan").selectOption("email");
  await page.getByLabel("Nilai pencarian").fill("lookup@example.test");
  await page.getByRole("button", { name: "Cari anggota" }).click();
  await expect(page.locator("tbody tr")).toHaveCount(1);
  await expect(page.getByLabel("Nilai pencarian")).toHaveValue("");
  expect(new URL(page.url()).search).toBe("");
});

for (const role of ["analyst", "auditor"] as const) test(`${role} has a separate workspace and no record navigation`, async ({ page }) => {
  await mock(page, role);
  await page.goto("/dashboard");
  await expect(page).toHaveURL(new RegExp(role === "analyst" ? "/analytics$" : "/audit$"));
  await expect(page.locator("tbody tr")).toHaveCount(1);
  expect(await page.getByRole("link", { name: "Daftar anggota", exact: true }).count()).toBe(0);
  await page.goto("/anggota/1");
  await expect(page.getByRole("alert").filter({ hasText: "tidak memiliki akses" })).toBeVisible();
});

test("finance is read-only and anggota has its own scoped directory", async ({ page }) => {
  await mock(page, "finance_officer", { rekening: "0000000000000123", npwp: "000000000000123" });
  await page.goto("/anggota/1");
  await expect(page.getByText("0000000000000123", { exact: true })).toBeVisible();
  expect(await page.getByRole("button", { name: "Perbarui kontak" }).count()).toBe(0);
  await page.unroute("**/api/**");
  await mock(page, "anggota");
  await page.goto("/anggota");
  await expect(page.getByText("Record milik sendiri", { exact: true })).toBeVisible();
});

test("privileged officer can insert source fields without crypto metadata", async ({ page }) => {
  await mock(page, "privileged_officer");
  await page.goto("/anggota/baru");
  await page.getByLabel("Nama *", { exact: true }).fill("Anggota Uji Baru");
  await page.getByLabel("Pengguna *", { exact: true }).fill("uji-baru");
  const request = page.waitForRequest(r => r.url().endsWith("/api/anggota") && r.method() === "POST");
  await page.getByRole("button", { name: "Simpan anggota" }).click();
  const body = (await request).postDataJSON();
  expect(Object.keys(body)).toHaveLength(29);
  expect(body).not.toHaveProperty("dek_pii_wrapped");
  expect(body.pengguna).toBe("uji-baru");
  await expect(page).toHaveURL(/\/anggota\/1$/);
});

test("mobile navigation stays within viewport", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await mock(page, "operator");
  await page.goto("/anggota");
  await page.getByRole("button", { name: "Buka navigasi" }).click();
  await page.getByRole("link", { name: "Profil & hak akses", exact: true }).click();
  await expect(page.getByRole("heading", { level: 1 })).toHaveText("Profil & hak akses");
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
});

test("analytics shows only released marginals and sends dimension/label filters", async ({ page }) => {
  await mock(page, "analyst");
  await page.route("**/api/analytics/summary**", async route => {
    await route.fulfill({ json: { total: null, groups: [
      { dimension: "pekerjaan_terakhir", value: "Guru Uji", count: 6 },
      { dimension: "nama_bank", value: "Bank Uji", count: 5 },
      { dimension: "nama_kppn", value: null, count: 5 },
    ] } });
  });
  await page.goto("/analytics");
  await expect(page.locator("tbody tr")).toHaveCount(3);
  await expect(page.locator("tbody tr").filter({ hasText: "Guru Uji" }).locator("td").last()).toHaveText("6");
  await expect(page.locator("tbody tr").filter({ hasText: "Bank Uji" }).locator("td").last()).toHaveText("5");
  await expect(page.getByText("Tidak disediakan", { exact: true })).toBeVisible();
  await expect(page.getByText("Dokter", { exact: true })).toHaveCount(0);
  await expect(page.getByLabel("Label kelompok", { exact: true })).toBeDisabled();
  await page.getByLabel("Dimensi", { exact: true }).selectOption("pekerjaan_terakhir");
  await page.getByLabel("Label kelompok", { exact: true }).fill("Guru Uji");
  const request = page.waitForRequest(r => r.url().includes("/analytics/summary?") && r.url().includes("dimension="));
  await page.getByRole("button", { name: "Terapkan filter" }).click();
  const query = new URL((await request).url()).searchParams;
  expect([...query.keys()].sort()).toEqual(["dimension", "value"]);
  expect(query.get("dimension")).toBe("pekerjaan_terakhir");
  expect(query.get("value")).toBe("Guru Uji");
  expect(new URL(page.url()).search).toBe("");
});

test("analytics empty state omits small labels and escapes released text", async ({ page }) => {
  await mock(page, "analyst");
  let groups: { dimension: string; value: string; count: number }[] = [];
  await page.route("**/api/analytics/summary**", route => route.fulfill({ json: { total: null, groups } }));
  await page.goto("/analytics");
  await expect(page.getByRole("heading", { name: "Tidak ada kelompok yang dapat ditampilkan" })).toBeVisible();
  await expect(page.locator("tbody tr")).toHaveCount(0);
  groups = [{ dimension: "nama_bank", value: "<script>window.analyticsXss=true</script>", count: 5 }];
  await page.reload();
  await expect(page.locator("tbody td").filter({ hasText: "<script>window.analyticsXss=true</script>" })).toHaveCount(1);
  expect(await page.evaluate(() => Reflect.get(window, "analyticsXss"))).toBeUndefined();
});
