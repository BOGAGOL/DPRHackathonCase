"use client";
import { createContext, useContext, useEffect, useState } from "react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { ArrowUpRight, ChevronRight, Fingerprint, LayoutDashboard, List, LogOut, Menu, Search, ShieldCheck, Users, X, ClipboardList, CircleUserRound } from "lucide-react";
import { api, roleLabel, type User } from "@/lib/api";
import { Button } from "@/components/ui/button";
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
  useEffect(() => { api<User>("/auth/me").then(setUser).catch(e => setError(e.message)); }, []);
  async function logout() { try { await api("/auth/logout", { method: "POST" }); setUser(null); router.replace("/login"); router.refresh(); } catch (e) { setError((e as Error).message); } }
  const links = [{ href: "/dashboard", label: "Ringkasan", icon: LayoutDashboard }, { href: "/anggota", label: "Daftar anggota", icon: Users },
    ...(user?.permissions.includes("search:ktp") ? [{ href: "/pencarian", label: "Pencarian KTP", icon: Search }] : []),
    ...(user?.permissions.includes("audit:read") ? [{ href: "/audit", label: "Log aktivitas", icon: ClipboardList }] : []),
    ...(user?.permissions.includes("users:manage") ? [{ href: "/pengguna", label: "Kelola pengguna", icon: List }] : []), { href: "/profil", label: "Profil & hak akses", icon: CircleUserRound }];
  return <div className="app-shell"><aside className={`sidebar ${open ? "sidebar-open" : ""}`}><Link href="/dashboard" className="brand"><div className="brand-mark"><ShieldCheck size={24} /></div><span>DPR <strong>Secure</strong><small>DATA MANAGEMENT</small></span></Link><button className="mobile-close" aria-label="Tutup navigasi" onClick={() => setOpen(false)}><X /></button><div className="workspace-label">WORKSPACE <span>DEMO</span></div><nav>{links.map(item => <Link onClick={() => setOpen(false)} key={item.href} href={item.href} className={pathname === item.href || item.href === "/anggota" && pathname.startsWith("/anggota/") ? "nav-link active" : "nav-link"}><item.icon size={19} />{item.label}{pathname === item.href && <ChevronRight size={15} className="nav-arrow" />}</Link>)}</nav><div className="sidebar-bottom"><div className="protection-card"><ShieldCheck size={21} /><strong>Akses sesuai kewenangan</strong><p>Data yang ditampilkan mengikuti izin akun dan penugasan Anda.</p><Link href="/profil">Lihat hak akses <ArrowUpRight size={14} /></Link></div><div className="sidebar-foot"><Fingerprint size={16} /><span>Hackathon DPR RI 2026</span></div></div></aside><div className="workspace"><header className="topbar"><div className="breadcrumb"><button className="mobile-menu" aria-label="Buka navigasi" onClick={() => setOpen(true)}><Menu /></button><span>Workspace</span><ChevronRight size={14} /><strong>{links.find(l => l.href === pathname)?.label || "Profil anggota"}</strong></div><div className="session-status"><span className="status-dot" /> Sesi terautentikasi</div><div className="user-chip"><div className="avatar">{user?.username.slice(0, 2).toUpperCase() || "··"}</div><div><strong>{user?.username || "Memuat…"}</strong><small>{user ? roleLabel[user.role] : ""}</small></div><button aria-label="Keluar" title="Keluar" onClick={logout}><LogOut size={17} /></button></div></header><main><State error={error} loading={!user && !error}>{user && <UserContext.Provider value={user}>{children}</UserContext.Provider>}</State></main><footer className="main-footer"><span>© 2026 DPR Secure · Prototipe hackathon</span><span>Data sintetis untuk demonstrasi</span></footer></div></div>;
}
