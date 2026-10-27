"use client";
import { useEffect, useState } from "react";
import Link from "next/link";
import { ChevronLeft, ChevronRight, ShieldCheck, Plus } from "lucide-react";
import { api, canReadRecords, type MemberPage } from "@/lib/api";
import { PageHeading, State, useUser } from "@/components/shell";
import { Button } from "@/components/ui/button";
import { MemberTable } from "@/components/member-table";
export default function Members() {
  const user = useUser();
  const [data, setData] = useState<MemberPage>(), [page, setPage] = useState(1), [error, setError] = useState(""), [loading, setLoading] = useState(true), [retry, setRetry] = useState(0);
  useEffect(() => { if (!canReadRecords(user.role)) { setLoading(false); return; } const controller = new AbortController(); setLoading(true); setError(""); api<MemberPage>(`/anggota?page=${page}`, { signal: controller.signal }).then(setData).catch(e => { if (e.name !== "AbortError") setError(e.message); }).finally(() => { if (!controller.signal.aborted) setLoading(false); }); return () => controller.abort(); }, [page, retry, user.role]);
  return <><PageHeading eyebrow="DIREKTORI" title="Data anggota" description="Daftar mengikuti cakupan record dan masking dari server.">{user.role === "privileged_officer" ? <Button asChild><Link href="/anggota/baru"><Plus size={15} /> Tambah anggota</Link></Button> : <span className="badge"><ShieldCheck size={14} /> {user.role === "anggota" ? "Record milik sendiri" : "Cakupan sesuai peran"}</span>}</PageHeading>{!canReadRecords(user.role) ? <State error="Peran ini tidak memiliki akses record anggota." /> : <section className="card"><div className="card-heading"><div><h3>Direktori anggota</h3><p>50 anggota per halaman. Nama termasking mengikuti peran akun.</p></div></div><State loading={loading} error={error}>{data && <><MemberTable members={data.items} /><div className="pagination"><span>{data.total ? (page - 1) * data.page_size + 1 : 0}–{Math.min(page * data.page_size, data.total)} dari <strong>{data.total}</strong> anggota</span><div><Button aria-label="Halaman sebelumnya" variant="outline" size="sm" disabled={page === 1} onClick={() => setPage(p => p - 1)}><ChevronLeft size={15} /></Button><span>Halaman {page}</span><Button aria-label="Halaman berikutnya" variant="outline" size="sm" disabled={page * data.page_size >= data.total} onClick={() => setPage(p => p + 1)}><ChevronRight size={15} /></Button></div></div></>}</State>{error && <Button className="m-4" variant="outline" onClick={() => setRetry(r => r + 1)}>Coba lagi</Button>}</section>}<div className="page-note"><ShieldCheck size={16} /> Data yang tidak diizinkan tidak disertakan dalam respons API.</div></>;
}
