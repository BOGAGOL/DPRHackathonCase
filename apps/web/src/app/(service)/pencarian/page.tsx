"use client";
import { useState } from "react";
import { Search, LockKeyhole } from "lucide-react";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import { api, type Member } from "@/lib/api";
import { PageHeading, State, useUser } from "@/components/shell";
import { Button } from "@/components/ui/button";
import { MemberTable } from "@/components/member-table";
const schema = z.object({ no_ktp: z.string().trim().min(1, "Masukkan nomor KTP").max(128) });
export default function SearchPage() {
  const user = useUser(), [result, setResult] = useState<Member[]>(), [error, setError] = useState("");
  const { register, handleSubmit, reset, formState: { errors, isSubmitting } } = useForm<z.infer<typeof schema>>({ resolver: zodResolver(schema) });
  async function search(value: z.infer<typeof schema>) { setError(""); setResult(undefined); try { setResult(await api<Member[]>("/anggota/search/ktp", { method: "POST", body: JSON.stringify(value) })); reset(); } catch (e) { setError((e as Error).message); } }
  return <><PageHeading eyebrow="PENCARIAN TERBATAS" title="Temukan berdasarkan KTP" description="Pencarian kecocokan persis untuk anggota dalam penugasan Anda." />{!user.permissions.includes("search:ktp") ? <State error="Anda tidak memiliki izin pencarian KTP." /> : <><section className="card search-card"><div className="stat-icon green"><LockKeyhole size={24} /></div><h3>Verifikasi identitas anggota</h3><p>Masukkan nomor lengkap sesuai data sintetis. Panjang nomor dummy dapat berbeda dari NIK resmi.</p><form onSubmit={handleSubmit(search)}><label htmlFor="ktp">Nomor KTP</label><div className="search-row"><input id="ktp" type="password" autoComplete="off" placeholder="Masukkan nomor KTP" {...register("no_ktp")} /><Button disabled={isSubmitting}><Search size={17} />{isSubmitting ? "Mencari…" : "Cari anggota"}</Button></div>{errors.no_ktp && <small className="field-error">{errors.no_ktp.message}</small>}</form><div className="inline-note">Hasil mengikuti hak akses record. Nomor pencarian tidak disimpan dalam riwayat URL atau audit.</div></section><State error={error} loading={isSubmitting}>{result && <section className="card"><div className="card-heading"><h3>Hasil pencarian</h3><span className="badge">{result.length} ditemukan</span></div><MemberTable members={result} /></section>}</State></>}</>;
}
