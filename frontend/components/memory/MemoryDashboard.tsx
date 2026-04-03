"use client";

import { useState, useEffect, useCallback } from "react";
import { api, Memory, MemorySearchResult, MemoryType } from "@/lib/api";
import MemoryCard from "./MemoryCard";

interface Props {
  onLogout: () => void;
}

const PLATFORMS = ["All", "chatgpt", "claude", "cursor", "notion"];
const TYPES: Array<{ label: string; value: MemoryType | "all" }> = [
  { label: "All", value: "all" },
  { label: "Long-term", value: "long_term" },
  { label: "Short-term", value: "short_term" },
  { label: "Semantic", value: "semantic" },
];

export default function MemoryDashboard({ onLogout }: Props) {
  const [memories, setMemories] = useState<Memory[]>([]);
  const [searchResults, setSearchResults] = useState<MemorySearchResult[] | null>(null);
  const [searchQuery, setSearchQuery] = useState("");
  const [filterType, setFilterType] = useState<MemoryType | "all">("all");
  const [filterPlatform, setFilterPlatform] = useState("All");
  const [loading, setLoading] = useState(true);
  const [searching, setSearching] = useState(false);
  const [contextPrompt, setContextPrompt] = useState("");
  const [contextResult, setContextResult] = useState<string | null>(null);
  const [activeTab, setActiveTab] = useState<"memories" | "search" | "context">("memories");

  const loadMemories = useCallback(async () => {
    setLoading(true);
    try {
      const data = await api.listMemories({
        memory_type: filterType === "all" ? undefined : filterType,
        platform: filterPlatform === "All" ? undefined : filterPlatform,
        limit: 50,
      });
      setMemories(data);
    } catch (err) {
      console.error(err);
    } finally {
      setLoading(false);
    }
  }, [filterType, filterPlatform]);

  useEffect(() => { loadMemories(); }, [loadMemories]);

  async function handleSearch(e: React.FormEvent) {
    e.preventDefault();
    if (!searchQuery.trim()) return;
    setSearching(true);
    try {
      const results = await api.searchMemories(searchQuery);
      setSearchResults(results);
    } catch (err) {
      console.error(err);
    } finally {
      setSearching(false);
    }
  }

  async function handleGetContext(e: React.FormEvent) {
    e.preventDefault();
    if (!contextPrompt.trim()) return;
    setSearching(true);
    try {
      const result = await api.getContext(contextPrompt);
      setContextResult(result.augmented_prompt);
    } catch (err) {
      console.error(err);
    } finally {
      setSearching(false);
    }
  }

  async function handleDelete(id: string) {
    await api.deleteMemory(id);
    setMemories((prev) => prev.filter((m) => m.id !== id));
    if (searchResults) {
      setSearchResults((prev) => prev?.filter((r) => r.memory.id !== id) ?? null);
    }
  }

  const totalLongTerm = memories.filter((m) => m.memory_type === "long_term").length;
  const totalShortTerm = memories.filter((m) => m.memory_type === "short_term").length;

  return (
    <div className="min-h-screen flex flex-col">
      {/* Top nav */}
      <header className="border-b border-slate-800 bg-slate-950 sticky top-0 z-10">
        <div className="max-w-5xl mx-auto px-4 py-3 flex items-center gap-4">
          <span className="text-xl">🧠</span>
          <span className="font-semibold text-white">AI Memory Layer</span>

          {/* Stats */}
          <div className="hidden sm:flex items-center gap-4 text-sm ml-4">
            <span className="text-slate-400">
              <span className="text-violet-400 font-medium">{totalLongTerm}</span> long-term
            </span>
            <span className="text-slate-400">
              <span className="text-blue-400 font-medium">{totalShortTerm}</span> short-term
            </span>
          </div>

          <button
            onClick={() => { api.clearToken(); onLogout(); }}
            className="ml-auto text-sm text-slate-400 hover:text-white transition-colors"
          >
            Sign out
          </button>
        </div>
      </header>

      <div className="max-w-5xl mx-auto px-4 py-6 w-full flex-1">
        {/* Tab bar */}
        <div className="flex gap-1 bg-slate-900 p-1 rounded-lg mb-6 w-fit">
          {(["memories", "search", "context"] as const).map((tab) => (
            <button
              key={tab}
              onClick={() => setActiveTab(tab)}
              className={`px-4 py-1.5 rounded-md text-sm font-medium transition-colors capitalize ${
                activeTab === tab ? "bg-slate-700 text-white" : "text-slate-400 hover:text-white"
              }`}
            >
              {tab}
            </button>
          ))}
        </div>

        {/* ── Memories tab ── */}
        {activeTab === "memories" && (
          <>
            {/* Filters */}
            <div className="flex flex-wrap gap-3 mb-6">
              <div>
                <span className="text-xs text-slate-500 block mb-1">Type</span>
                <div className="flex gap-1">
                  {TYPES.map((t) => (
                    <button
                      key={t.value}
                      onClick={() => setFilterType(t.value)}
                      className={`px-3 py-1 text-xs rounded-full transition-colors ${
                        filterType === t.value
                          ? "bg-indigo-600 text-white"
                          : "bg-slate-800 text-slate-400 hover:text-white"
                      }`}
                    >
                      {t.label}
                    </button>
                  ))}
                </div>
              </div>
              <div>
                <span className="text-xs text-slate-500 block mb-1">Platform</span>
                <div className="flex gap-1">
                  {PLATFORMS.map((p) => (
                    <button
                      key={p}
                      onClick={() => setFilterPlatform(p)}
                      className={`px-3 py-1 text-xs rounded-full transition-colors capitalize ${
                        filterPlatform === p
                          ? "bg-indigo-600 text-white"
                          : "bg-slate-800 text-slate-400 hover:text-white"
                      }`}
                    >
                      {p}
                    </button>
                  ))}
                </div>
              </div>
            </div>

            {loading ? (
              <div className="grid gap-3 sm:grid-cols-2">
                {Array.from({ length: 6 }).map((_, i) => (
                  <div key={i} className="bg-slate-900 border border-slate-800 rounded-xl p-4 h-40 animate-pulse" />
                ))}
              </div>
            ) : memories.length === 0 ? (
              <div className="text-center py-20 text-slate-500">
                <div className="text-4xl mb-3">🧠</div>
                <p>No memories yet.</p>
                <p className="text-sm mt-1">Install the browser extension to start capturing AI conversations.</p>
              </div>
            ) : (
              <div className="grid gap-3 sm:grid-cols-2">
                {memories.map((m) => (
                  <MemoryCard key={m.id} memory={m} onDelete={handleDelete} />
                ))}
              </div>
            )}
          </>
        )}

        {/* ── Search tab ── */}
        {activeTab === "search" && (
          <>
            <form onSubmit={handleSearch} className="flex gap-3 mb-6">
              <input
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                placeholder="Search your memories semantically…"
                className="flex-1 bg-slate-900 border border-slate-700 rounded-lg px-4 py-2.5 text-sm text-white placeholder-slate-500 focus:outline-none focus:border-indigo-500"
              />
              <button
                type="submit"
                disabled={searching}
                className="bg-indigo-600 hover:bg-indigo-500 disabled:opacity-50 text-white px-5 py-2.5 rounded-lg text-sm font-medium"
              >
                {searching ? "…" : "Search"}
              </button>
            </form>

            {searchResults !== null && (
              searchResults.length === 0 ? (
                <p className="text-slate-500 text-sm">No matching memories found.</p>
              ) : (
                <div className="grid gap-3 sm:grid-cols-2">
                  {searchResults.map((r) => (
                    <MemoryCard
                      key={r.memory.id}
                      memory={r.memory}
                      onDelete={handleDelete}
                      similarityScore={r.similarity_score}
                    />
                  ))}
                </div>
              )
            )}
          </>
        )}

        {/* ── Context tab ── */}
        {activeTab === "context" && (
          <div className="max-w-2xl">
            <p className="text-sm text-slate-400 mb-4">
              Enter a prompt and see how your memory context will be injected before sending it to an AI system.
            </p>
            <form onSubmit={handleGetContext} className="space-y-3">
              <textarea
                value={contextPrompt}
                onChange={(e) => setContextPrompt(e.target.value)}
                rows={4}
                placeholder="Write email to my manager about the project status…"
                className="w-full bg-slate-900 border border-slate-700 rounded-lg px-4 py-3 text-sm text-white placeholder-slate-500 focus:outline-none focus:border-indigo-500 resize-none"
              />
              <button
                type="submit"
                disabled={searching}
                className="bg-indigo-600 hover:bg-indigo-500 disabled:opacity-50 text-white px-5 py-2.5 rounded-lg text-sm font-medium"
              >
                {searching ? "Retrieving context…" : "Get Augmented Prompt"}
              </button>
            </form>

            {contextResult && (
              <div className="mt-6">
                <h3 className="text-sm font-medium text-slate-300 mb-2">Augmented prompt:</h3>
                <pre className="bg-slate-900 border border-slate-700 rounded-lg p-4 text-xs text-slate-300 whitespace-pre-wrap overflow-auto max-h-80">
                  {contextResult}
                </pre>
                <button
                  onClick={() => navigator.clipboard.writeText(contextResult)}
                  className="mt-2 text-xs text-indigo-400 hover:text-indigo-300"
                >
                  Copy to clipboard
                </button>
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
