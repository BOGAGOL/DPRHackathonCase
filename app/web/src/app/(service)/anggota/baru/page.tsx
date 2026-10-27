"use client";
import { useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import { ArrowLeft, Save } from "lucide-react";
import { api, fieldLabel, type Detail } from "@/lib/api";
import { PageHeading, State, useUser } from "@/components/shell";
import { Button } from "@/components/ui/button";
const fields = ["nama", "nama_lengkap", "nama_tanpa_gelar", "jenis_kelamin", "tempat_lahir", "tanggal_lahir", "tanggal_pernikahan", "no_ktp", "pekerjaan_terakhir", "alamat_jakarta", "telpon_jakarta", "alamat_daerah", "telpon_daerah", "handphone", "email", "ruangan", "status_kawin", "jumlah_anak", "jumlah_tanggungan", "jumlah_jiwa", "rekening", "nama_rekening", "npwp", "nama_kppn", "nip_kppn", "nama_bank", "kode_bank", "pengguna", "agama"];
const schema = z.record(z.string(), z.string().max(255)).superRefine((values, ctx) => {
  for (const field of ["nama", "pengguna"]) if (!values[field]?.trim() || values[field].length > 100) ctx.addIssue({ code: "custom", path: [field], message: "Wajib diisi, maksimum 100 karakter." });
  if (values.email && !z.email().safeParse(values.email).success) ctx.addIssue({ code: "custom", path: ["email"], message: "Email tidak valid." });
  if (values.no_ktp && !/^\d{14}(\d{2})?$/.test(values.no_ktp)) ctx.addIssue({ code: "custom", path: ["no_ktp"], message: "Gunakan 14 digit dummy atau 16 digit NIK." });
  for (const field of ["handphone", "telpon_jakarta", "telpon_daerah"]) if (values[field] && (!/^[0-9+() .-]+$/.test(values[field]) || values[field].length > 40)) ctx.addIssue({ code: "custom", path: [field], message: "Nomor telepon tidak valid." });
  for (const field of ["jumlah_anak", "jumlah_tanggungan", "jumlah_jiwa"]) if (values[field] && !/^\d+$/.test(values[field])) ctx.addIssue({ code: "custom", path: [field], message: "Gunakan bilangan bulat non-negatif." });
});
export default function CreateMember() {
  const user = useUser(), router = useRouter(), [error, setError] = useState("");
  const { register, handleSubmit, formState: { errors, isSubmitting } } = useForm<Record<string, string>>({ resolver: zodResolver(schema) });
  async function save(values: Record<string, string>) { setError(""); const payload = Object.fromEntries(fields.map(field => [field, values[field] === "" ? null : values[field]])); try { const result = await api<Detail>("/anggota", { method: "POST", body: JSON.stringify(payload) }); router.replace(`/anggota/${encodeURIComponent(result.anggota_id)}`); } catch (e) { setError((e as Error).message); } }
  return <><Link href="/anggota" className="back-link"><ArrowLeft size={16} /> Kembali ke direktori</Link><PageHeading eyebrow="ADMINISTRASI ANGGOTA" title="Tambah anggota" description="Masukkan data sintetis yang memang diizinkan untuk layanan." />{user.role !== "privileged_officer" ? <State error="Hanya petugas berwenang dapat menambah anggota." /> : <section className="card"><div className="card-heading"><div><h3>Informasi anggota baru</h3><p>Nama dan pengguna wajib diisi. Nilai kosong lainnya dikirim sebagai NULL.</p></div></div><form className="contact-form" onSubmit={handleSubmit(save)}><State error={error} /><div className="form-grid">{fields.map(field => <div key={field}><label htmlFor={field}>{fieldLabel[field]}{["nama", "pengguna"].includes(field) ? " *" : ""}</label><input id={field} type={field.startsWith("tanggal_") ? "date" : "text"} autoComplete="off" {...register(field)} />{errors[field] && <small className="field-error">{errors[field]?.message}</small>}</div>)}</div><div className="inline-note">Field keuangan yang dimasukkan tidak otomatis dikembalikan dalam respons untuk peran ini.</div><div className="form-actions"><Button disabled={isSubmitting}><Save size={15} />{isSubmitting ? "Menyimpan…" : "Simpan anggota"}</Button></div></form></section>}</>;
}
