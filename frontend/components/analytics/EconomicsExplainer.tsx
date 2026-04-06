"use client";

import { Info } from "lucide-react";
import { AnalyticsSummary, formatTokens } from "@/lib/analytics";

interface Props {
  summary: AnalyticsSummary;
}

function Row({ label, value, highlight }: { label: string; value: string; highlight?: boolean }) {
  return (
    <div className="flex items-center justify-between py-2 border-b border-slate-800 last:border-0">
      <span className="text-sm text-slate-400">{label}</span>
      <span className={`text-sm font-semibold ${highlight ? "text-emerald-400" : "text-slate-200"}`}>
        {value}
      </span>
    </div>
  );
}

export default function EconomicsExplainer({ summary }: Props) {
  const hasData = summary.total_queries > 0;

  const origTokens = hasData ? summary.avg_original_tokens : 15_000;
  const memTokens = hasData
    ? summary.avg_memory_tokens
    : Math.round(15_000 / Math.max(summary.avg_compression_ratio, 1));
  const savedTokens = origTokens - memTokens;
  const costPer1M = summary.cost_per_million_tokens || 3.0;
  const savedPerQuery = (savedTokens * costPer1M) / 1_000_000;

  return (
    <div className="bg-slate-900 border border-slate-800 rounded-2xl p-5">
      <div className="flex items-start gap-2 mb-4">
        <div className="p-1.5 bg-indigo-900/50 rounded-lg mt-0.5">
          <Info className="w-4 h-4 text-indigo-400" />
        </div>
        <div>
          <h2 className="text-base font-semibold text-white">How We Calculate Savings</h2>
          <p className="text-xs text-slate-500 mt-0.5">Per-query economics breakdown</p>
        </div>
      </div>

      <div className="space-y-0">
        <Row
          label="Avg original context"
          value={`~${formatTokens(origTokens)} tokens`}
        />
        <Row
          label="Avg memory context"
          value={`${formatTokens(memTokens)} tokens`}
        />
        <Row
          label="Tokens saved per query"
          value={`${formatTokens(savedTokens)} tokens`}
          highlight
        />
        <Row
          label="Cost rate"
          value={`$${costPer1M.toFixed(2)} / 1M tokens`}
        />
        <Row
          label="Savings per query"
          value={`$${savedPerQuery.toFixed(4)}`}
          highlight
        />
        {hasData && (
          <Row
            label={`× ${summary.total_queries.toLocaleString()} queries`}
            value={`$${(savedPerQuery * summary.total_queries).toFixed(2)} total`}
            highlight
          />
        )}
      </div>

      {/* Formula note */}
      <div className="mt-4 bg-slate-800/60 rounded-xl px-3 py-3 text-xs text-slate-400 font-mono leading-relaxed">
        <p className="text-slate-300 font-sans font-medium text-xs mb-1.5">Formula</p>
        <p>savings = (orig_tokens − mem_tokens)</p>
        <p className="mt-0.5 pl-12">× (cost_per_1M ÷ 1,000,000)</p>
        <p className="mt-0.5 pl-12">× num_queries</p>
      </div>

      <p className="text-xs text-slate-600 mt-3">
        Token counts are averaged across all providers. Cost rate reflects blended pricing.
      </p>
    </div>
  );
}
