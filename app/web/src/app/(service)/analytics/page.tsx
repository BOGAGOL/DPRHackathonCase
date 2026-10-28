"use client";
import { useEffect, useState } from "react";
import { ChartNoAxesCombined, ShieldCheck } from "lucide-react";
import { api, fieldLabel, type Analytics, type AggregateCount } from "@/lib/api";
import { PageHeading, State, useUser } from "@/components/shell";
const dimensions = ["jenis_kelamin", "pekerjaan_terakhir", "nama_kppn", "nama_bank", "age_band"];
const displayCount = (count: AggregateCount) => count === null ? "Disembunyikan" : typeof count === "number" ? count.toLocaleString("id-ID") : count;
export default function AnalyticsPage() {
  const user = useUser();
  const [data, setData] = useState<Analytics>();
  const [error, setError] = useState("");
  const [filters, setFilters] = useState<Record<string, string>>({});
  const [query, setQuery] = useState("");
  useEffect(() => {
    if (user.role !== "analyst") { setError("Endpoint agregat hanya tersedia untuk analyst."); return; }
    const controller = new AbortController();
    setData(undefined); setError("");
    api<Analytics>(`/analytics/summary${query ? `?${query}` : ""}`, { signal: controller.signal })
      .then(setData).catch(e => { if (e.name !== "AbortError") setError(e.message); });
    return () => controller.abort();
  }, [user.role, query]);
  return <>
    <PageHeading eyebrow="ANALISIS TERBATAS" title="Ringkasan agregat" description="Statistik tanpa nama, kontak, atau identitas anggota. Kelompok 1-4 anggota ditampilkan sebagai <5." />
    <form className="card" onSubmit={e => { e.preventDefault(); setQuery(new URLSearchParams(Object.entries(filters).filter(([, value]) => value !== "")).toString()); }}>
      <div className="card-heading"><h3>Filter agregat</h3></div>
      <div className="form-grid">{dimensions.map(field => <label key={field}>{fieldLabel[field] || "Kelompok usia"}
        <input aria-label={fieldLabel[field] || "Kelompok usia"} maxLength={field === "age_band" ? 10 : 50} value={filters[field] || ""}
          placeholder={field === "age_band" ? "40-49" : field === "jenis_kelamin" ? "L / P" : "Semua"}
          onChange={e => setFilters(previous => ({ ...previous, [field]: e.target.value }))} />
      </label>)}</div>
      <button type="submit" className="btn-primary">Terapkan filter</button>
      <button type="button" className="btn-secondary" onClick={() => { setFilters({}); setQuery(""); }}>Reset filter</button>
    </form>
    <p className="notice">Jumlah kecil disensor oleh server. Total atau jumlah pembanding dapat disembunyikan agar angka kecil tidak dapat dihitung lewat pengurangan.</p>
    <State error={error} loading={!data && !error}>{data && <>
      <div className="stat-card"><div className="stat-top"><span>Anggota dalam proyeksi</span><div className="stat-icon green"><ChartNoAxesCombined size={20} /></div></div><div className="stat-number">{displayCount(data.total)}</div><small>Agregat sesuai filter</small></div>
      <section className="card"><div className="card-heading"><h3>Distribusi operasional</h3><ShieldCheck size={19} /></div><div className="table-scroll"><table><thead><tr><th>DIMENSI</th><th>KELOMPOK</th><th>JUMLAH</th></tr></thead><tbody>{data.groups.map((g, i) => <tr key={`${g.dimension}:${i}`}><td>{fieldLabel[g.dimension] || "Kelompok usia"}</td><td>{g.value ?? "Tidak tersedia"}</td><td>{displayCount(g.count)}</td></tr>)}</tbody></table>{!data.groups.length && <div className="empty-state"><h3>Belum ada kelompok</h3></div>}</div></section>
    </>}</State>
  </>;
}
