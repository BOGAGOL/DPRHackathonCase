"use client";
import { useState } from "react";
import { Search, LockKeyhole } from "lucide-react";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import { api, canReadRecords, type MemberPage } from "@/lib/api";
import { PageHeading, State, useUser } from "@/components/shell";
import { Button } from "@/components/ui/button";
import { MemberTable } from "@/components/member-table";
const schema = z.object({ field: z.enum(["no_ktp", "email"]), value: z.string().trim().min(1, "Masukkan nilai pencarian").max(150) }).superRefine((input, ctx) => { if (input.field === "no_ktp" && !/^\d{14}(\d{2})?$/.test(input.value.replace(/\s/g, ""))) ctx.addIssue({ code: "custom", path: ["value"], message: "Gunakan 14 digit dummy atau 16 digit NIK." }); if (input.field === "email" && !z.email().safeParse(input.value).success) ctx.addIssue({ code: "custom", path: ["value"], message: "Format email tidak valid." }); });
export default function SearchPage() {
  const user = useUser(), [result, setResult] = useState<MemberPage>(), [error, setError] = useState("");
  const { register, handleSubmit, resetField, formState: { errors, isSubmitting } } = useForm<z.infer<typeof schema>>({ resolver: zodResolver(schema), defaultValues: { field: "no_ktp", value: "" } });
  async function search(input: z.infer<typeof schema>) { setError(""); setResult(undefined); try { const params = new URLSearchParams({ [input.field]: input.value }); setResult(await api<MemberPage>(`/anggota/search?${params.toString()}`)); resetField("value"); } catch (e) { setError((e as Error).message); } }
  return <><PageHeading eyebrow="PENCARIAN TERBATAS" title="Pencarian identitas" description="Temukan kecocokan persis nomor KTP atau email dalam cakupan akun." />{!canReadRecords(user.role) ? <State error="Peran ini tidak memiliki akses pencarian anggota." /> : <><section className="card search-card"><div className="stat-icon green"><LockKeyhole size={24} /></div><h3>Verifikasi anggota</h3><p>Nomor KTP dummy 14 digit dipertahankan. Masukkan identitas hanya untuk keperluan yang diizinkan.</p><form onSubmit={handleSubmit(search)}><label htmlFor="search-field">Cari berdasarkan</label><select id="search-field" {...register("field")}><option value="no_ktp">Nomor KTP</option><option value="email">Email</option></select><label htmlFor="search-value">Nilai pencarian</label><div className="search-row"><input id="search-value" type="password" autoComplete="off" placeholder="Masukkan nilai lengkap" {...register("value")} /><Button disabled={isSubmitting}><Search size={17} />{isSubmitting ? "Mencari…" : "Cari anggota"}</Button></div>{errors.value && <small className="field-error">{errors.value.message}</small>}</form><div className="inline-note">Pencarian dikirim langsung ke API. Nilai tidak dimasukkan ke alamat halaman atau penyimpanan browser.</div></section><State error={error} loading={isSubmitting}>{result && <section className="card"><div className="card-heading"><h3>Hasil pencarian</h3><span className="badge">{result.total} ditemukan</span></div><MemberTable members={result.items} /></section>}</State></>}</>;
}
