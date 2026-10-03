"use client";

import { useRouter } from "next/navigation";
import { useEffect } from "react";

import { homePath, useAuth } from "@/lib/auth";

export default function Home() {
  const { user, loading } = useAuth();
  const router = useRouter();

  useEffect(() => {
    if (loading) return;
    router.replace(user ? homePath(user.role) : "/login");
  }, [user, loading, router]);

  return null;
}
