"use client";

import { DollarSign, Zap, Layers, Target, TrendingUp, TrendingDown, Minus } from "lucide-react";
import { AnalyticsSummary, formatUsd, formatTokens, formatPct } from "@/lib/analytics";

interface Props {
  summary: AnalyticsSummary;
  isDemo?: boolean;
}

interface StatCardProps {
  label: string;
  value: string;
  trend: number;
  icon: React.ReactNode;
  accentClass: string;
  bgClass: string;
  borderClass: string;
}

function TrendBadge({ pct }: { pct: number }) {
  if (pct === 0) {
    return (
      <span className="inline-flex items-center gap-1 text-xs text-slate-500">
        <Minus className="w-3 h-3" />
        —
      </span>
    );
  }
  const positive = pct > 0;
  return (
    <span
      className={`inline-flex items-center gap-0.5 text-xs font-medium ${
        positive ? "text-emerald-400" : "text-red-400"
      }`}
    >
      {positive ? (
        <TrendingUp className="w-3 h-3" />
      ) : (
        <TrendingDown className="w-3 h-3" />
      )}
      {positive ? "+" : ""}
      {pct.toFixed(1)}%
    </span>
  );
}

function StatCard({ label, value, trend, icon, accentClass, bgClass, borderClass }: StatCardProps) {
  return (
    <div
      className={`relative overflow-hidden rounded-2xl border ${borderClass} ${bgClass} p-5 flex flex-col gap-3`}
    >
      {/* Subtle glow orb */}
      <div
        className={`absolute -top-6 -right-6 w-24 h-24 rounded-full opacity-10 blur-2xl ${accentClass}`}
      />

      <div className="flex items-start justify-between">
        <div className={`p-2 rounded-xl ${accentClass} bg-opacity-15`}>
          {icon}
        </div>
        <TrendBadge pct={trend} />
      </div>

      <div>
        <p className="text-3xl font-bold text-white tracking-tight leading-none">{value}</p>
        <p className="text-xs text-slate-400 mt-1.5 font-medium uppercase tracking-wider">{label}</p>
      </div>

      <p className="text-xs text-slate-500">vs last period</p>
    </div>
  );
}

export default function EconomicsOverview({ summary, isDemo }: Props) {
  const stats: StatCardProps[] = [
    {
      label: "Total Cost Saved",
      value: formatUsd(summary.total_cost_saved_usd),
      trend: summary.cost_saved_trend_pct,
      icon: <DollarSign className="w-5 h-5 text-emerald-400" />,
      accentClass: "bg-emerald-500",
      bgClass: "bg-gradient-to-br from-slate-900 to-emerald-950/30",
      borderClass: "border-emerald-900/60",
    },
    {
      label: "Tokens Saved",
      value: formatTokens(summary.total_tokens_saved),
      trend: summary.tokens_saved_trend_pct,
      icon: <Zap className="w-5 h-5 text-yellow-400" />,
      accentClass: "bg-yellow-500",
      bgClass: "bg-gradient-to-br from-slate-900 to-yellow-950/20",
      borderClass: "border-yellow-900/50",
    },
    {
      label: "Avg Compression Ratio",
      value:
        summary.avg_compression_ratio > 0
          ? `${summary.avg_compression_ratio.toFixed(1)}×`
          : "—",
      trend: summary.compression_trend_pct,
      icon: <Layers className="w-5 h-5 text-violet-400" />,
      accentClass: "bg-violet-500",
      bgClass: "bg-gradient-to-br from-slate-900 to-violet-950/30",
      borderClass: "border-violet-900/50",
    },
    {
      label: "Memory Hit Rate",
      value:
        summary.memory_hit_rate > 0
          ? formatPct(summary.memory_hit_rate)
          : "—",
      trend: summary.hit_rate_trend_pct,
      icon: <Target className="w-5 h-5 text-sky-400" />,
      accentClass: "bg-sky-500",
      bgClass: "bg-gradient-to-br from-slate-900 to-sky-950/30",
      borderClass: "border-sky-900/50",
    },
  ];

  return (
    <div className="space-y-3">
      {isDemo && (
        <div className="flex items-center gap-2 bg-indigo-950/60 border border-indigo-800/60 rounded-xl px-4 py-2.5 text-sm text-indigo-300">
          <span className="text-base">✨</span>
          <span>
            <strong>Demo data</strong> — start using mem-ai to see your real savings here.
          </span>
        </div>
      )}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
        {stats.map((s) => (
          <StatCard key={s.label} {...s} />
        ))}
      </div>
    </div>
  );
}
