import type { Metadata } from "next";
import "./globals.css";
export const metadata: Metadata = { title: "DPR Secure · Manajemen Data Anggota", description: "Aplikasi layanan pengelolaan data anggota dengan kontrol akses. Demonstrasi data sintetis Hackathon DPR RI 2026." };
export default function RootLayout({ children }: { children: React.ReactNode }) { return <html lang="id"><body>{children}</body></html>; }
