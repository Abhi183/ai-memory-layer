"use client";

import { useState, useEffect } from "react";
import { RefreshCw, AlertCircle } from "lucide-react";
import {
  getAnalyticsSummary,
  getAnalyticsTimeline,
  getProviderBreakdown,
  AnalyticsSummary,
  TimelinePoint,
  ProviderStat,
  DEMO_SUMMARY,
  DEMO_TIMELINE,
  DEMO_PROVIDERS,
} from "@/lib/analytics";
import EconomicsOverview from "@/components/analytics/EconomicsOverview";
import TokenSavingsChart from "@/components/analytics/TokenSavingsChart";
import ProviderBreakdown from "@/components/analytics/ProviderBreakdown";
import CompressionGauge from "@/components/analytics/CompressionGauge";
import EconomicsExplainer from "@/components/analytics/EconomicsExplainer";

type Range = 7 | 14 | 30 | 90;

const RANGES: Range[] = [7, 14, 30, 90];

export default function AnalyticsPage() {
  const [summary, setSummary] = useState<AnalyticsSummary | null>(null);
  const [timeline, setTimeline] = useState<TimelinePoint[]>([]);
  const [providers, setProviders] = useState<ProviderStat[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [isDemo, setIsDemo] = useState(false);
  const [range, setRange] = useState<Range>(30);
  const [refreshing, setRefreshing] = useState(false);

  async function load(days: Range, isRefresh = false) {
    if (isRefresh) {
      setRefreshing(true);
    } else {
      setLoading(true);
    }
    setError(null);

    try {
      const [sum, tl, prov] = await Promise.all([
        getAnalyticsSummary(days),
        getAnalyticsTimeline(days),
        getProviderBreakdown(),
      ]);

      // If no queries recorded yet, show demo data
      if (sum.total_queries === 0) {
        setSummary(DEMO_SUMMARY);
        setTimeline(DEMO_TIMELINE);
        setProviders(DEMO_PROVIDERS);
        setIsDemo(true);
      } else {
        setSummary(sum);
        setTimeline(tl);
        setProviders(prov);
        setIsDemo(false);
      }
    } catch {
      // API not available — fall back to demo data so the page is always useful
      setSummary(DEMO_SUMMARY);
      setTimeline(DEMO_TIMELINE);
      setProviders(DEMO_PROVIDERS);
      setIsDemo(true);
      setError(null); // Don't show error, just show demo
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }

  useEffect(() => {
    load(range);
  }, [range]);

  function handleRangeChange(r: Range) {
    setRange(r);
  }

  if (loading) {
    return (
      <div className="min-h-screen bg-slate-950 flex items-center justify-center">
        <div className="flex flex-col items-center gap-3 text-slate-400">
          <div className="w-8 h-8 border-2 border-violet-500 border-t-transparent rounded-full animate-spin" />
          <p className="text-sm">Loading analytics…</p>
        </div>
      </div>
    );
  }

  if (!summary) return null;

  return (
    <div className="min-h-screen bg-slate-950 text-slate-100">
      {/* Page header */}
      <div className="border-b border-slate-800 bg-slate-950/80 backdrop-blur-sm sticky top-0 z-10">
        <div className="max-w-6xl mx-auto px-4 py-3 flex items-center gap-4">
          <div className="flex items-center gap-2">
            <span className="text-xl">📊</span>
            <span className="font-semibold text-white">Economics Dashboard</span>
          </div>

          {/* Range selector */}
          <div className="ml-auto flex items-center gap-1 bg-slate-900 p-0.5 rounded-lg">
            {RANGES.map((r) => (
              <button
                key={r}
                onClick={() => handleRangeChange(r)}
                className={`px-3 py-1.5 text-xs font-medium rounded-md transition-colors ${
                  range === r
                    ? "bg-slate-700 text-white"
                    : "text-slate-400 hover:text-white"
                }`}
              >
                {r}d
              </button>
            ))}
          </div>

          <button
            onClick={() => load(range, true)}
            disabled={refreshing}
            className="p-1.5 text-slate-400 hover:text-white disabled:opacity-40 transition-colors"
            title="Refresh"
          >
            <RefreshCw className={`w-4 h-4 ${refreshing ? "animate-spin" : ""}`} />
          </button>
        </div>
      </div>

      <div className="max-w-6xl mx-auto px-4 py-6 space-y-5">
        {/* Error banner (non-blocking) */}
        {error && (
          <div className="flex items-center gap-3 bg-red-950/50 border border-red-800/60 rounded-xl px-4 py-3 text-sm text-red-300">
            <AlertCircle className="w-4 h-4 shrink-0" />
            {error}
          </div>
        )}

        {/* Row 1: Stat cards */}
        <EconomicsOverview summary={summary} isDemo={isDemo} />

        {/* Row 2: Chart (wide) */}
        <TokenSavingsChart data={timeline} />

        {/* Row 3: Provider breakdown + Gauge side by side */}
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-5">
          <div className="lg:col-span-2">
            <ProviderBreakdown providers={providers} />
          </div>
          <div className="space-y-5">
            <CompressionGauge ratio={summary.avg_compression_ratio} />
          </div>
        </div>

        {/* Row 4: Explainer */}
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-5">
          <EconomicsExplainer summary={summary} />

          {/* Quick-stats table */}
          <div className="bg-slate-900 border border-slate-800 rounded-2xl p-5">
            <h2 className="text-base font-semibold text-white mb-4">Period Summary</h2>
            <div className="space-y-0">
              {[
                { label: "Total queries", value: summary.total_queries.toLocaleString() },
                { label: "Memories invoked", value: summary.total_memories_used.toLocaleString() },
                { label: "Hit rate", value: `${summary.memory_hit_rate.toFixed(1)}%` },
                { label: "Avg tokens saved / query", value: summary.total_queries > 0 ? Math.round(summary.total_tokens_saved / summary.total_queries).toLocaleString() : "—" },
                { label: "Avg cost saved / query", value: summary.total_queries > 0 ? `$${(summary.total_cost_saved_usd / summary.total_queries).toFixed(4)}` : "—" },
                { label: "Period", value: `Last ${summary.period_days} days` },
              ].map(({ label, value }) => (
                <div
                  key={label}
                  className="flex items-center justify-between py-2 border-b border-slate-800 last:border-0"
                >
                  <span className="text-sm text-slate-400">{label}</span>
                  <span className="text-sm font-semibold text-slate-200">{value}</span>
                </div>
              ))}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
