"use client";
import { useEffect } from "react";
import { useRouter } from "next/navigation";
import { useUser, State } from "@/components/shell";
import { homeForRole } from "@/lib/api";
export default function Dashboard() { const user = useUser(), router = useRouter(); useEffect(() => { router.replace(homeForRole(user.role)); }, [user.role, router]); return <State loading />; }
