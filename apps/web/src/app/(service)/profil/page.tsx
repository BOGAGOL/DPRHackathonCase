"use client";
import { ShieldCheck, UserRound } from "lucide-react";
import { roleLabel } from "@/lib/api";
import { PageHeading, useUser } from "@/components/shell";
export default function Profile() { const user = useUser(); return <><PageHeading eyebrow="AKUN ANDA" title="Profil & hak akses" description="Peran dan izin efektif untuk sesi ini." /><section className="card profile-card"><div className="stat-icon green"><UserRound /></div><h2>{user.username}</h2><span className="badge">{roleLabel[user.role]}</span><hr /><h3>Permission efektif</h3><div className="permission-list">{user.permissions.length ? user.permissions.map(p => <div key={p}><ShieldCheck size={16} /><code>{p}</code></div>) : <p>Akses profil publik: nama, ID anggota, dan ruangan.</p>}</div><div className="inline-note">Penugasan record tetap berlaku meskipun izin field telah diberikan. Hubungi administrator untuk perubahan akses.</div></section></>; }
