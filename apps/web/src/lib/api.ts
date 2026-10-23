export type User = { id: number; username: string; role: string; permissions: string[] };
export type Member = { id: number; nama: string; ruangan: string | null };
export type Detail = Member & { fields: Record<string, string | null>; masked_fields: string[]; editable_fields: string[]; revision: number };
export class ApiError extends Error { constructor(public status: number, message: string) { super(message); } }
export async function api<T>(path: string, options: RequestInit = {}): Promise<T> {
  const method = options.method || "GET";
  const headers = new Headers(options.headers);
  if (options.body) headers.set("Content-Type", "application/json");
  if (method !== "GET") {
    const token = document.cookie.split("; ").find(row => row.startsWith("dpr_csrf="))?.split("=")[1];
    if (token) headers.set("X-CSRF-Token", decodeURIComponent(token));
  }
  const response = await fetch(`/api${path}`, { ...options, headers, credentials: "same-origin", cache: "no-store" });
  let data;
  try { data = await response.json(); } catch { throw new ApiError(response.status, "Layanan tidak tersedia. Coba lagi."); }
  if (!response.ok) {
    if (response.status === 401 && path !== "/auth/login" && typeof window !== "undefined" && window.location.pathname !== "/login") window.location.assign("/login");
    throw new ApiError(response.status, typeof data.detail === "string" ? data.detail : "Permintaan gagal");
  }
  return data as T;
}
export const roleLabel: Record<string, string> = { public: "Public viewer", operator: "Operator", staff: "Authorized staff", admin: "Administrator" };
export const fieldLabel: Record<string, string> = { email: "Email", handphone: "Handphone", telpon_jakarta: "Telepon Jakarta", telpon_daerah: "Telepon daerah", alamat_jakarta: "Alamat Jakarta", alamat_daerah: "Alamat daerah", no_ktp: "Nomor KTP", tanggal_lahir: "Tanggal lahir", rekening: "Nomor rekening", nama_rekening: "Nama rekening", nama_bank: "Bank", npwp: "NPWP" };
