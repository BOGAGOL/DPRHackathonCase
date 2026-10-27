"use client";
import { createContext, useContext, useEffect, useState } from "react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { ArrowUpRight, ChevronRight, Fingerprint, LogOut, Menu, Search, ShieldCheck, Users, X, ClipboardList, CircleUserRound, ChartNoAxesCombined } from "lucide-react";
import { api, canReadRecords, homeForRole, roleLabel, type User } from "@/lib/api";
const UserContext = createContext<User | null>(null);
export function useUser() { const user = useContext(UserContext); if (!user) throw new Error("Session context missing"); return user; }
export function State({ error, loading, children }: { error?: string; loading?: boolean; children?: React.ReactNode }) {
  if (error) return <div className="notice notice-error" role="alert">{error}</div>;
  if (loading) return <div className="loading" role="status"><span className="spinner" /> Memuat data…</div>;
  return <>{children}</>;
}
export function PageHeading({ eyebrow, title, description, children }: { eyebrow: string; title: string; description: string; children?: React.ReactNode }) { return <div className="page-heading"><div><div className="eyebrow">{eyebrow}</div><h1>{title}</h1><p>{description}</p></div>{children}</div>; }
export function Shell({ children }: { children: React.ReactNode }) {
  const [user, setUser] = useState<User | null>(null), [error, setError] = useState(""), [open, setOpen] = useState(false);
  const pathname = usePathname(), router = useRouter();
  useEffect(() => { const controller = new AbortController(); api<User>("/auth/me", { signal: controller.signal }).then(setUser).catch(e => { if (e.name !== "AbortError") setError(e.message); }); return () => controller.abort(); }, []);
  async function logout() { try { await api("/auth/logout", { method: "POST" }); setUser(null); router.replace("/login"); router.refresh(); } catch (e) { setError((e as Error).message); } }
  const links = [
    ...(user && canReadRecords(user.role) ? [{ href: "/anggota", label: "Daftar anggota", icon: Users }, { href: "/pencarian", label: "Pencarian identitas", icon: Search }] : []),
    ...(user?.role === "analyst" ? [{ href: "/analytics", label: "Ringkasan agregat", icon: ChartNoAxesCombined }] : []),
    ...(user?.role === "auditor" ? [{ href: "/audit", label: "Log audit", icon: ClipboardList }] : []),
    { href: "/profil", label: "Profil & hak akses", icon: CircleUserRound }
  ];
  return <div className="app-shell"><aside className={`sidebar ${open ? "sidebar-open" : ""}`}><Link href={user ? homeForRole(user.role) : "/login"} className="brand"><div className="brand-mark"><ShieldCheck size={24} /></div><span>DPR <strong>Secure</strong><small>LAYANAN ANGGOTA</small></span></Link><button className="mobile-close" aria-label="Tutup navigasi" onClick={() => setOpen(false)}><X /></button><div className="workspace-label">WORKSPACE <span>DEMO</span></div><nav>{links.map(item => <Link onClick={() => setOpen(false)} key={item.href} href={item.href} className={pathname === item.href || item.href === "/anggota" && pathname.startsWith("/anggota/") ? "nav-link active" : "nav-link"}><item.icon size={19} />{item.label}{pathname === item.href && <ChevronRight size={15} className="nav-arrow" />}</Link>)}</nav><div className="sidebar-bottom"><div className="protection-card"><ShieldCheck size={21} /><strong>Akses sesuai kewenangan</strong><p>Layanan membatasi record dan field sebelum respons dikirim ke browser.</p><Link href="/profil">Lihat peran akun <ArrowUpRight size={14} /></Link></div><div className="sidebar-foot"><Fingerprint size={16} /><span>Hackathon DPR RI 2026 · Modul B</span></div></div></aside><div className="workspace"><header className="topbar"><div className="breadcrumb"><button className="mobile-menu" aria-label="Buka navigasi" onClick={() => setOpen(true)}><Menu /></button><span>Workspace</span><ChevronRight size={14} /><strong>{links.find(l => l.href === pathname)?.label || "Profil anggota"}</strong></div><div className="session-status"><span className="status-dot" /> Sesi terautentikasi</div><div className="user-chip"><div className="avatar">{user?.username.slice(0, 2).toUpperCase() || "··"}</div><div><strong>{user?.username || "Memuat…"}</strong><small>{user ? roleLabel[user.role] : ""}</small></div><button aria-label="Keluar" title="Keluar" onClick={logout}><LogOut size={17} /></button></div></header><main><State error={error} loading={!user && !error}>{user && <UserContext.Provider value={user}>{children}</UserContext.Provider>}</State></main><footer className="main-footer"><span>© 2026 DPR Secure · Prototipe hackathon</span><span>Data sintetis · Hak akses diterapkan server</span></footer></div></div>;
}
