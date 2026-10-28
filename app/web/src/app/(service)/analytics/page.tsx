"use client";
import { useEffect, useState } from "react";
import { ChartNoAxesCombined, ShieldCheck } from "lucide-react";
import { api, fieldLabel, type Analytics } from "@/lib/api";
import { PageHeading, State, useUser } from "@/components/shell";
const dimensions = ["jenis_kelamin", "pekerjaan_terakhir", "nama_kppn", "nama_bank", "age_band"];
export default function AnalyticsPage() {
  const user = useUser();
  const [data, setData] = useState<Analytics>();
  const [error, setError] = useState("");
  const [filters, setFilters] = useState({ dimension: "", value: "" });
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
    <PageHeading eyebrow="ANALISIS TERBATAS" title="Ringkasan agregat" description="Statistik tanpa identitas anggota. Kelompok berisi kurang dari 5 anggota beserta labelnya tidak ditampilkan." />
    <form className="card" onSubmit={e => { e.preventDefault(); setQuery(new URLSearchParams(Object.entries(filters).filter(([, value]) => value !== "")).toString()); }}>
      <div className="card-heading"><h3>Pilih agregat yang tersedia</h3></div>
      <div className="form-grid">
        <label>Dimensi<select aria-label="Dimensi" value={filters.dimension} onChange={e => setFilters({ dimension: e.target.value, value: "" })}>
          <option value="">Semua dimensi</option>
          {dimensions.map(field => <option key={field} value={field}>{fieldLabel[field] || "Kelompok usia"}</option>)}
        </select></label>
        <label>Label kelompok<input aria-label="Label kelompok" maxLength={50} disabled={!filters.dimension} value={filters.value}
          placeholder="Semua label yang tersedia" onChange={e => setFilters(previous => ({ ...previous, value: e.target.value }))} /></label>
      </div>
      <button type="submit" className="btn-primary">Terapkan filter</button>
      <button type="button" className="btn-secondary" onClick={() => { setFilters({ dimension: "", value: "" }); setQuery(""); }}>Reset filter</button>
    </form>
    <p className="notice">Setiap dimensi dihitung terpisah. Filter gabungan antaratribut anggota belum didukung. Total anggota tidak disediakan.</p>
    <State error={error} loading={!data && !error}>{data && <>
      <div className="stat-card"><div className="stat-top"><span>Total anggota</span><div className="stat-icon green"><ChartNoAxesCombined size={20} /></div></div><div className="stat-number">Tidak disediakan</div><small>Total tidak dihitung dari penjumlahan kelompok.</small></div>
      <section className="card"><div className="card-heading"><h3>Distribusi operasional</h3><ShieldCheck size={19} /></div><div className="table-scroll"><table><thead><tr><th>DIMENSI</th><th>KELOMPOK</th><th>JUMLAH</th></tr></thead><tbody>{data.groups.map((g, i) => <tr key={`${g.dimension}:${i}`}><td>{fieldLabel[g.dimension] || "Kelompok usia"}</td><td>{g.value ?? "Tidak tersedia"}</td><td>{g.count.toLocaleString("id-ID")}</td></tr>)}</tbody></table>{!data.groups.length && <div className="empty-state"><h3>Tidak ada kelompok yang dapat ditampilkan</h3><p>Kelompok berisi kurang dari 5 anggota beserta labelnya tidak ditampilkan.</p></div>}</div></section>
    </>}</State>
  </>;
}
