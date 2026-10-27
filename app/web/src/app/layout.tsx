import type { Metadata } from "next";
import { headers } from "next/headers";
import "./globals.css";
export const dynamic = "force-dynamic";
export const metadata: Metadata = { title: "DPR Secure · Layanan Anggota", description: "Aplikasi layanan anggota dengan kontrol akses per peran dan per record." };
export default async function RootLayout({ children }: { children: React.ReactNode }) {
  await headers();
  return <html lang="id"><body>{children}</body></html>;
}
