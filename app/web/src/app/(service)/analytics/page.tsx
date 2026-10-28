"use client";
import { useEffect, useState } from "react";
import { RotateCcw, Search, ShieldCheck, SlidersHorizontal } from "lucide-react";
import { api, fieldLabel, type Analytics } from "@/lib/api";
import { PageHeading, State, useUser } from "@/components/shell";
import { Button } from "@/components/ui/button";
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
    <PageHeading eyebrow="ANALISIS TERBATAS" title="Ringkasan agregat" description="Kelompok kurang dari 5 anggota tidak ditampilkan." />
    <form className="card analytics-filter" aria-labelledby="analytics-filter-title" onSubmit={e => { e.preventDefault(); setQuery(new URLSearchParams(Object.entries(filters).filter(([, value]) => value !== "")).toString()); }}>
      <div className="card-heading">
        <h2 id="analytics-filter-title"><SlidersHorizontal size={17} aria-hidden="true" /> Filter statistik</h2>
        {query && <span className="badge badge-green">Filter aktif</span>}
      </div>
      <div className="analytics-filter-body">
        <div className="analytics-filter-fields">
          <div className="analytics-field">
            <label htmlFor="analytics-dimension">Dimensi</label>
            <select id="analytics-dimension" value={filters.dimension} onChange={e => setFilters({ dimension: e.target.value, value: "" })}>
              <option value="">Semua dimensi</option>
              {dimensions.map(field => <option key={field} value={field}>{fieldLabel[field] || "Kelompok usia"}</option>)}
            </select>
          </div>
          <div className="analytics-field">
            <label htmlFor="analytics-label">Label kelompok</label>
            <input id="analytics-label" maxLength={50} disabled={!filters.dimension} value={filters.value}
              placeholder={filters.dimension ? "Semua kelompok" : "Pilih dimensi terlebih dahulu"}
              onChange={e => setFilters(previous => ({ ...previous, value: e.target.value }))} />
          </div>
        </div>
        <div className="analytics-filter-actions">
          <Button type="submit"><Search size={16} aria-hidden="true" /> Terapkan</Button>
          <Button type="button" variant="outline" disabled={!filters.dimension && !filters.value && !query}
            onClick={() => { setFilters({ dimension: "", value: "" }); setQuery(""); }}>
            <RotateCcw size={16} aria-hidden="true" /> Reset
          </Button>
        </div>
      </div>
    </form>
    <div className="analytics-results"><State error={error} loading={!data && !error}>{data &&
      <section className="card" aria-labelledby="analytics-results-title">
        <div className="card-heading"><h2 id="analytics-results-title">Distribusi anggota</h2><ShieldCheck size={19} aria-hidden="true" /></div>
        <div className="table-scroll"><table><thead><tr><th>DIMENSI</th><th>KELOMPOK</th><th>JUMLAH</th></tr></thead>
          <tbody>{data.groups.map((g, i) => <tr key={`${g.dimension}:${i}`}><td>{fieldLabel[g.dimension] || "Kelompok usia"}</td><td>{g.value ?? "Tidak tersedia"}</td><td>{g.count.toLocaleString("id-ID")}</td></tr>)}</tbody>
        </table>{!data.groups.length && <div className="empty-state"><h3>Tidak ada hasil</h3><p>Ubah atau reset filter.</p></div>}</div>
      </section>
    }</State></div>
  </>;
}
