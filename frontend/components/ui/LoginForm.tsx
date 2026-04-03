"use client";

import { useState } from "react";
import { api } from "@/lib/api";

interface Props {
  onSuccess: () => void;
}

export default function LoginForm({ onSuccess }: Props) {
  const [mode, setMode] = useState<"login" | "register">("login");
  const [email, setEmail] = useState("");
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError("");
    setLoading(true);
    try {
      if (mode === "login") {
        await api.login(email, password);
      } else {
        await api.register(email, username, password);
        await api.login(email, password);
      }
      onSuccess();
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Something went wrong");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="flex items-center justify-center min-h-screen p-4">
      <div className="w-full max-w-sm">
        {/* Logo */}
        <div className="text-center mb-8">
          <div className="text-5xl mb-3">🧠</div>
          <h1 className="text-2xl font-bold text-white">AI Memory Layer</h1>
          <p className="text-slate-400 text-sm mt-1">Universal memory for your AI tools</p>
        </div>

        <div className="bg-slate-900 border border-slate-800 rounded-xl p-6">
          {/* Mode toggle */}
          <div className="flex rounded-lg bg-slate-800 p-1 mb-6">
            {(["login", "register"] as const).map((m) => (
              <button
                key={m}
                onClick={() => setMode(m)}
                className={`flex-1 py-1.5 text-sm font-medium rounded-md transition-colors ${
                  mode === m ? "bg-slate-600 text-white" : "text-slate-400 hover:text-white"
                }`}
              >
                {m === "login" ? "Sign In" : "Register"}
              </button>
            ))}
          </div>

          <form onSubmit={handleSubmit} className="space-y-4">
            <div>
              <label className="block text-xs text-slate-400 mb-1 uppercase tracking-wide">Email</label>
              <input
                type="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                required
                className="w-full bg-slate-800 border border-slate-700 rounded-lg px-3 py-2 text-sm text-white placeholder-slate-500 focus:outline-none focus:border-indigo-500"
                placeholder="you@example.com"
              />
            </div>

            {mode === "register" && (
              <div>
                <label className="block text-xs text-slate-400 mb-1 uppercase tracking-wide">Username</label>
                <input
                  type="text"
                  value={username}
                  onChange={(e) => setUsername(e.target.value)}
                  required
                  minLength={3}
                  className="w-full bg-slate-800 border border-slate-700 rounded-lg px-3 py-2 text-sm text-white placeholder-slate-500 focus:outline-none focus:border-indigo-500"
                  placeholder="johndoe"
                />
              </div>
            )}

            <div>
              <label className="block text-xs text-slate-400 mb-1 uppercase tracking-wide">Password</label>
              <input
                type="password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                required
                minLength={8}
                className="w-full bg-slate-800 border border-slate-700 rounded-lg px-3 py-2 text-sm text-white placeholder-slate-500 focus:outline-none focus:border-indigo-500"
                placeholder="••••••••"
              />
            </div>

            {error && (
              <div className="bg-red-950 border border-red-800 rounded-lg px-3 py-2 text-sm text-red-300">
                {error}
              </div>
            )}

            <button
              type="submit"
              disabled={loading}
              className="w-full bg-indigo-600 hover:bg-indigo-500 disabled:opacity-50 text-white font-medium py-2.5 rounded-lg text-sm transition-colors"
            >
              {loading ? "Please wait…" : mode === "login" ? "Sign In" : "Create Account"}
            </button>
          </form>
        </div>
      </div>
    </div>
  );
}
