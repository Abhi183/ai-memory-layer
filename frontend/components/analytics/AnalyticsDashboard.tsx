"use client";

import { useState, useEffect } from "react";
import { RefreshCw } from "lucide-react";
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
import EconomicsOverview from "./EconomicsOverview";
import TokenSavingsChart from "./TokenSavingsChart";
import ProviderBreakdown from "./ProviderBreakdown";
import CompressionGauge from "./CompressionGauge";
import EconomicsExplainer from "./EconomicsExplainer";

type Range = 7 | 14 | 30 | 90;
const RANGES: Range[] = [7, 14, 30, 90];

export default function AnalyticsDashboard() {
  const [summary, setSummary] = useState<AnalyticsSummary | null>(null);
  const [timeline, setTimeline] = useState<TimelinePoint[]>([]);
  const [providers, setProviders] = useState<ProviderStat[]>([]);
  const [loading, setLoading] = useState(true);
  const [isDemo, setIsDemo] = useState(false);
  const [range, setRange] = useState<Range>(30);
  const [refreshing, setRefreshing] = useState(false);

  async function load(days: Range, isRefresh = false) {
    if (isRefresh) {
      setRefreshing(true);
    } else {
      setLoading(true);
    }

    try {
      const [sum, tl, prov] = await Promise.all([
        getAnalyticsSummary(days),
        getAnalyticsTimeline(days),
        getProviderBreakdown(),
      ]);

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
      // API not reachable — show demo so the dashboard is always useful
      setSummary(DEMO_SUMMARY);
      setTimeline(DEMO_TIMELINE);
      setProviders(DEMO_PROVIDERS);
      setIsDemo(true);
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }

  useEffect(() => {
    load(range);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [range]);

  if (loading) {
    return (
      <div className="flex items-center justify-center py-20">
        <div className="flex flex-col items-center gap-3 text-slate-400">
          <div className="w-7 h-7 border-2 border-violet-500 border-t-transparent rounded-full animate-spin" />
          <p className="text-sm">Loading analytics…</p>
        </div>
      </div>
    );
  }

  if (!summary) return null;

  return (
    <div className="space-y-5">
      {/* Sub-header: range selector + refresh */}
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-base font-semibold text-white">Economics & Savings</h2>
          <p className="text-xs text-slate-500 mt-0.5">
            How much the memory layer saves you on every AI query
          </p>
        </div>
        <div className="flex items-center gap-2">
          <div className="flex items-center gap-0.5 bg-slate-900 p-0.5 rounded-lg">
            {RANGES.map((r) => (
              <button
                key={r}
                onClick={() => setRange(r)}
                className={`px-2.5 py-1 text-xs font-medium rounded transition-colors ${
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
            title="Refresh data"
          >
            <RefreshCw className={`w-4 h-4 ${refreshing ? "animate-spin" : ""}`} />
          </button>
        </div>
      </div>

      {/* Stat cards */}
      <EconomicsOverview summary={summary} isDemo={isDemo} />

      {/* Timeline chart */}
      <TokenSavingsChart data={timeline} />

      {/* Provider breakdown + compression gauge */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-5">
        <div className="lg:col-span-2">
          <ProviderBreakdown providers={providers} />
        </div>
        <CompressionGauge ratio={summary.avg_compression_ratio} />
      </div>

      {/* Explainer + period stats */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-5">
        <EconomicsExplainer summary={summary} />

        <div className="bg-slate-900 border border-slate-800 rounded-2xl p-5">
          <h2 className="text-base font-semibold text-white mb-4">Period Summary</h2>
          <div className="space-y-0">
            {[
              { label: "Total queries", value: summary.total_queries.toLocaleString() },
              { label: "Memories invoked", value: summary.total_memories_used.toLocaleString() },
              { label: "Hit rate", value: `${summary.memory_hit_rate.toFixed(1)}%` },
              {
                label: "Avg tokens saved / query",
                value:
                  summary.total_queries > 0
                    ? Math.round(
                        summary.total_tokens_saved / summary.total_queries
                      ).toLocaleString()
                    : "—",
              },
              {
                label: "Avg cost saved / query",
                value:
                  summary.total_queries > 0
                    ? `$${(
                        summary.total_cost_saved_usd / summary.total_queries
                      ).toFixed(4)}`
                    : "—",
              },
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
  );
}
