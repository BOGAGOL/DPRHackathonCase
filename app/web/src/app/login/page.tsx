"use client";
import { useState } from "react";
import { useRouter } from "next/navigation";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import { ArrowRight, ShieldCheck } from "lucide-react";
import { Button } from "@/components/ui/button";
import { api } from "@/lib/api";
const schema = z.object({ username: z.string().min(1, "Masukkan username").max(64), password: z.string().min(1, "Masukkan password").max(256) });
export default function Login() {
  const router = useRouter(), [error, setError] = useState("");
  const { register, handleSubmit, formState: { errors, isSubmitting } } = useForm<z.infer<typeof schema>>({ resolver: zodResolver(schema) });
  async function login(values: z.infer<typeof schema>) { setError(""); try { await api("/auth/csrf"); await api("/auth/login", { method: "POST", body: JSON.stringify(values) }); router.replace("/dashboard"); router.refresh(); } catch (e) { setError((e as Error).message); } }
  return <main className="login-screen">
    <div className="login-container">
      <div className="brand"><div className="brand-mark"><ShieldCheck size={24} aria-hidden="true" /></div><span>DPR <strong>Secure</strong></span></div>
      <section className="card login-card" aria-labelledby="login-title">
        <h1 id="login-title">Masuk</h1>
        <form onSubmit={handleSubmit(login)}>
          <label htmlFor="username">Username</label>
          <input id="username" autoComplete="username" {...register("username")} />
          {errors.username && <small className="field-error">{errors.username.message}</small>}
          <label htmlFor="password">Password</label>
          <input id="password" type="password" autoComplete="current-password" {...register("password")} />
          {errors.password && <small className="field-error">{errors.password.message}</small>}
          {error && <div role="alert" className="notice notice-error">{error}</div>}
          <Button disabled={isSubmitting} type="submit">{isSubmitting ? "Memverifikasi…" : "Masuk ke aplikasi"}<ArrowRight size={17} aria-hidden="true" /></Button>
        </form>
      </section>
    </div>
  </main>;
}
