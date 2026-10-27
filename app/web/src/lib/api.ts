export type Role = "operator" | "privileged_officer" | "finance_officer" | "analyst" | "auditor" | "anggota";
export type User = { id: string; username: string; role: Role };
export type Member = { anggota_id: string; nama: string | null };
export type MemberPage = { items: Member[]; total: number; page: number; page_size: number };
export type Detail = Member & Record<string, string | number | null>;
export type AuditEvent = { id: string | number; actor: string | null; role: string; action: string; anggota_id: string | null; field_class: string | string[]; decision: string; request_id: string; created_at: string };
export type AuditPage = { items: AuditEvent[]; total: number; page: number; page_size: number };
export type Analytics = { total: number; groups: { dimension: string; value: string | null; count: number }[] };
export class ApiError extends Error { constructor(public status: number, message: string) { super(message); } }

export async function api<T>(path: string, options: RequestInit = {}): Promise<T> {
  const method = (options.method || "GET").toUpperCase();
  const headers = new Headers(options.headers);
  if (options.body) headers.set("Content-Type", "application/json");
  if (!["GET", "HEAD"].includes(method)) {
    const entry = document.cookie.split("; ").find(row => row.startsWith("dpr_csrf="));
    if (entry) headers.set("X-CSRF-Token", decodeURIComponent(entry.slice("dpr_csrf=".length)));
  }
  const response = await fetch(`/api${path}`, { ...options, headers, credentials: "same-origin", cache: "no-store", referrerPolicy: "no-referrer" });
  let data: unknown;
  try { data = await response.json(); } catch { throw new ApiError(response.status, "Layanan sementara tidak tersedia."); }
  if (!response.ok) {
    if (response.status === 401 && path !== "/auth/login" && window.location.pathname !== "/login") window.location.replace("/login");
    const detail = data && typeof data === "object" && "detail" in data ? data.detail : null;
    throw new ApiError(response.status, typeof detail === "string" ? detail : "Permintaan ditolak atau belum dapat diproses.");
  }
  return data as T;
}

export const roleLabel: Record<Role, string> = { operator: "Operator", privileged_officer: "Petugas berwenang", finance_officer: "Petugas keuangan", analyst: "Analis", auditor: "Auditor", anggota: "Anggota" };
export const canReadRecords = (role: Role) => !["analyst", "auditor"].includes(role);
export const canEditContact = (role: Role) => ["operator", "privileged_officer", "anggota"].includes(role);
export const homeForRole = (role: Role) => role === "analyst" ? "/analytics" : role === "auditor" ? "/audit" : "/anggota";
export const fieldLabel: Record<string, string> = { nama: "Nama", nama_lengkap: "Nama lengkap", nama_tanpa_gelar: "Nama tanpa gelar", email: "Email", handphone: "Handphone", telpon_jakarta: "Telepon Jakarta", telpon_daerah: "Telepon daerah", alamat_jakarta: "Alamat Jakarta", alamat_daerah: "Alamat daerah", no_ktp: "Nomor KTP", jenis_kelamin: "Jenis kelamin", tempat_lahir: "Tempat lahir", tanggal_lahir: "Tanggal lahir", tanggal_pernikahan: "Tanggal pernikahan", pekerjaan_terakhir: "Pekerjaan terakhir", ruangan: "Ruangan", status_kawin: "Status kawin", jumlah_anak: "Jumlah anak", jumlah_tanggungan: "Jumlah tanggungan", jumlah_jiwa: "Jumlah jiwa", rekening: "Nomor rekening", nama_rekening: "Nama rekening", nama_bank: "Bank", npwp: "NPWP", nama_kppn: "Nama KPPN", nip_kppn: "NIP KPPN", kode_bank: "Kode bank", pengguna: "Pengguna", agama: "Agama" };
