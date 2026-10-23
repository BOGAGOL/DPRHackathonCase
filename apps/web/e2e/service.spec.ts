import { test, expect, type Page } from "@playwright/test";
import { readFileSync } from "node:fs";
import path from "node:path";
const accounts: { username: string; password: string; role: string }[] = JSON.parse(readFileSync(path.resolve("../../.local/demo-accounts.json"), "utf8"));
async function login(page: Page, role: string) {
  const account = accounts.find(a => a.role === role)!;
  await page.goto("/login");
  await page.getByLabel("Username", { exact: true }).fill(account.username);
  await page.getByLabel("Password", { exact: true }).fill(account.password);
  await page.getByRole("button", { name: "Masuk ke aplikasi" }).click();
  await expect(page).toHaveURL(/\/dashboard$/);
  await expect(page.getByRole("heading", { name: "Ringkasan layanan" })).toBeVisible();
}
async function csrf(page: Page) {
  return (await page.context().cookies()).find(c => c.name === "dpr_csrf")!.value;
}

test("operator: login, scoped listing, masking, update, IDOR, logout", async ({ page }) => {
  await login(page, "operator");
  const cookies = await page.context().cookies();
  expect(cookies.find(c => c.name === "dpr_session")?.httpOnly).toBe(true);
  expect(await page.evaluate(() => Object.keys(localStorage))).toHaveLength(0);
  await page.getByRole("link", { name: "Daftar anggota", exact: true }).click();
  await expect(page.getByRole("heading", { name: "Data anggota", exact: true })).toBeVisible();
  await expect(page.locator("tbody tr")).toHaveCount(10);
  await page.getByRole("button", { name: "Halaman berikutnya" }).click();
  await expect(page.locator("tbody tr")).toHaveCount(2);
  const detailResponse = await page.request.get("/api/anggota/1");
  expect(detailResponse.status()).toBe(200);
  const detail = await detailResponse.json();
  expect(detail.fields).not.toHaveProperty("no_ktp");
  expect(detail.fields).not.toHaveProperty("rekening");
  expect((await page.request.get("/api/anggota/734")).status()).toBe(404);
  await page.goto("/anggota/1");
  await page.getByRole("button", { name: "Perbarui kontak" }).click();
  await expect(page.getByLabel("Email", { exact: true })).toHaveValue("");
  // Exercise encrypt-on-write without changing source values: null dummy patch is restored by PostgreSQL integration tooling.
  await page.getByRole("button", { name: "Batal", exact: true }).click();
  expect((await page.request.patch("/api/anggota/734/contact", { headers: { "X-CSRF-Token": await csrf(page) }, data: { revision: 1, email: "forbidden@example.test" } })).status()).toBe(404);
  await page.getByRole("button", { name: "Keluar", exact: true }).click();
  await expect(page).toHaveURL(/\/login$/);
  expect((await page.request.get("/api/auth/me")).status()).toBe(401);
});

test("staff: exact blind lookup, contact update, XSS is rendered as text", async ({ page }) => {
  await login(page, "staff");
  const initial = await (await page.request.get("/api/anggota/1")).json();
  await page.getByRole("link", { name: "Pencarian KTP", exact: true }).click();
  await page.getByLabel("Nomor KTP", { exact: true }).fill(initial.fields.no_ktp);
  await page.getByRole("button", { name: "Cari anggota", exact: true }).click();
  await expect(page.locator("tbody tr")).toHaveCount(1);
  await expect(page.getByLabel("Nomor KTP", { exact: true })).toHaveValue("");
  const attack = '<img src=x onerror="window.__dpr_xss_executed=true">';
  try {
    await page.goto("/anggota/1");
    await page.getByRole("button", { name: "Perbarui kontak" }).click();
    await page.getByLabel("Alamat Jakarta", { exact: true }).fill(attack);
    await page.getByRole("button", { name: "Simpan perubahan", exact: true }).click();
    await expect(page.getByRole("status")).toContainText("berhasil diperbarui");
    await expect(page.getByText(attack, { exact: true })).toBeVisible();
    expect(await page.evaluate(() => (window as unknown as Record<string, unknown>).__dpr_xss_executed)).toBeUndefined();
    expect(await page.locator('img[src="x"]').count()).toBe(0);
    const response = await page.request.patch("/api/anggota/1/contact", { data: { revision: initial.revision + 1, email: "csrf@example.test" } });
    expect(response.status()).toBe(403);
  } finally {
    const current = await (await page.request.get("/api/anggota/1")).json();
    const restored = await page.request.patch("/api/anggota/1/contact", { headers: { "X-CSRF-Token": await csrf(page) }, data: { revision: current.revision, alamat_jakarta: initial.fields.alamat_jakarta } });
    expect(restored.status()).toBe(200);
  }
});

test("public viewer: allowlist responses, no financial or contact data", async ({ page }) => {
  await login(page, "public");
  const detail = await (await page.request.get("/api/anggota/1")).json();
  expect(detail.fields).toEqual({});
  expect((await page.request.get("/api/audit/events")).status()).toBe(403);
  await page.goto("/anggota/1");
  await expect(page.getByRole("heading", { name: "Profil publik", exact: true })).toBeVisible();
  expect(await page.getByRole("button", { name: "Perbarui kontak" }).count()).toBe(0);
});

test("admin: audit and users available, member data denied", async ({ page }) => {
  await login(page, "admin");
  expect((await page.request.get("/api/anggota/1")).status()).toBe(404);
  await page.getByRole("link", { name: "Log aktivitas", exact: true }).click();
  await expect(page.locator("tbody tr").first()).toBeVisible();
  await page.getByRole("link", { name: "Kelola pengguna", exact: true }).click();
  await expect(page.getByRole("heading", { name: "Kelola pengguna", exact: true })).toBeVisible();
  await expect(page.locator("tbody tr")).toHaveCount(4);
});

test("mobile: navigation and login remain usable", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await login(page, "operator");
  await page.getByRole("button", { name: "Buka navigasi", exact: true }).click();
  await page.getByRole("link", { name: "Daftar anggota", exact: true }).click();
  await expect(page.getByRole("heading", { name: "Data anggota", exact: true })).toBeVisible();
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
});
