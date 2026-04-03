"use client";

import { useState, useEffect } from "react";
import { api } from "@/lib/api";
import MemoryDashboard from "@/components/memory/MemoryDashboard";
import LoginForm from "@/components/ui/LoginForm";

export default function Home() {
  const [authenticated, setAuthenticated] = useState<boolean | null>(null);

  useEffect(() => {
    setAuthenticated(api.isAuthenticated());
  }, []);

  if (authenticated === null) {
    return (
      <div className="flex items-center justify-center min-h-screen">
        <div className="w-6 h-6 border-2 border-indigo-500 border-t-transparent rounded-full animate-spin" />
      </div>
    );
  }

  if (!authenticated) {
    return <LoginForm onSuccess={() => setAuthenticated(true)} />;
  }

  return <MemoryDashboard onLogout={() => setAuthenticated(false)} />;
}
