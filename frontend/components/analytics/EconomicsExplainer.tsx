"use client";

import { Info } from "lucide-react";
import { AnalyticsSummary, formatTokens, formatUsd } from "@/lib/analytics";

interface Props {
  summary: AnalyticsSummary;
}

function Row({
  label,
  value,
  highlight,
  dimmed,
}: {
  label: string;
  value: string;
  highlight?: boolean;
  dimmed?: boolean;
}) {
  return (
    <div className="flex items-center justify-between py-2 border-b border-slate-800 last:border-0">
      <span className={`text-sm ${dimmed ? "text-slate-600" : "text-slate-400"}`}>{label}</span>
      <span
        className={`text-sm font-semibold ${
          highlight ? "text-emerald-400" : dimmed ? "text-slate-600" : "text-slate-200"
        }`}
      >
        {value}
      </span>
    </div>
  );
}

function Divider({ label }: { label: string }) {
  return (
    <div className="flex items-center gap-2 py-1.5">
      <div className="flex-1 border-t border-slate-800" />
      <span className="text-xs text-slate-600 uppercase tracking-wider">{label}</span>
      <div className="flex-1 border-t border-slate-800" />
    </div>
  );
}

export default function EconomicsExplainer({ summary }: Props) {
  const hasData = summary.total_queries > 0;
  const hasIngestionData = (summary.total_ingestion_cost_usd ?? 0) > 0 || hasData;

  const origTokens = hasData ? summary.avg_original_tokens : 15_000;
  const memTokens = hasData
    ? summary.avg_memory_tokens
    : Math.round(15_000 / Math.max(summary.avg_compression_ratio, 1));
  const savedTokens = origTokens - memTokens;
  const costPer1M = summary.cost_per_million_tokens || 3.0;
  const savedPerQuery = (savedTokens * costPer1M) / 1_000_000;

  // Ingestion cost constants (gpt-4o-mini rates, three pipeline steps)
  // Fact extraction: ~2000 in + 200 out
  // Summarization:   ~2000 in + 100 out
  // Classification:  ~100  in +   5 out
  const ingestionInputTokens = 6_200;
  const ingestionOutputTokens = 305;
  const ingestionCostPerMemory =
    (ingestionInputTokens * 0.15 + ingestionOutputTokens * 0.6) / 1_000_000;

  const totalIngestionCost = summary.total_ingestion_cost_usd ?? 0;
  const totalRetrievalSavings =
    summary.total_retrieval_savings_usd ?? summary.total_cost_saved_usd ?? 0;
  const netSavings = summary.net_savings_usd ?? totalRetrievalSavings - totalIngestionCost;

  const breakEven = summary.break_even_retrievals ?? 0;
  const breakEvenLabel =
    breakEven > 0 && breakEven < 1
      ? "< 1 retrieval"
      : breakEven >= 1
      ? `${breakEven.toFixed(2)} retrievals`
      : "—";

  return (
    <div className="bg-slate-900 border border-slate-800 rounded-2xl p-5">
      <div className="flex items-start gap-2 mb-4">
        <div className="p-1.5 bg-indigo-900/50 rounded-lg mt-0.5">
          <Info className="w-4 h-4 text-indigo-400" />
        </div>
        <div>
          <h2 className="text-base font-semibold text-white">Full ROI Breakdown</h2>
          <p className="text-xs text-slate-500 mt-0.5">Retrieval savings minus ingestion cost</p>
        </div>
      </div>

      <div className="space-y-0">
        <Divider label="Retrieval savings" />
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
          label="Retrieval savings per query"
          value={`$${savedPerQuery.toFixed(4)}`}
          highlight
        />
        {hasData && (
          <Row
            label={`× ${summary.total_queries.toLocaleString()} queries`}
            value={formatUsd(totalRetrievalSavings)}
            highlight
          />
        )}

        <Divider label="Ingestion cost (gpt-4o-mini)" />
        <Row
          label="Input tokens per memory"
          value={`~${ingestionInputTokens.toLocaleString()} tokens`}
          dimmed
        />
        <Row
          label="Output tokens per memory"
          value={`~${ingestionOutputTokens} tokens`}
          dimmed
        />
        <Row
          label="Ingestion cost per memory"
          value={`$${ingestionCostPerMemory.toFixed(5)}`}
        />
        {hasIngestionData && totalIngestionCost > 0 && (
          <Row
            label="Total ingestion cost"
            value={formatUsd(totalIngestionCost)}
          />
        )}

        <Divider label="Net ROI" />
        <Row
          label="Net savings (retrieval − ingestion)"
          value={hasData ? formatUsd(netSavings) : "—"}
          highlight
        />
        <Row
          label="Break-even retrievals per memory"
          value={breakEvenLabel}
        />
      </div>

      {/* Formula note */}
      <div className="mt-4 bg-slate-800/60 rounded-xl px-3 py-3 text-xs text-slate-400 font-mono leading-relaxed">
        <p className="text-slate-300 font-sans font-medium text-xs mb-1.5">Full cost equation</p>
        <p>C_net = C_retrieval_saved − C_ingestion</p>
        <p className="mt-1">C_retrieval_saved = (T_full − T_aug) / 1M × P_provider</p>
        <p className="mt-1">C_ingestion = (T_in × P_in + T_out × P_out) / 1M</p>
        <p className="mt-1 text-slate-500">
          At gpt-4o-mini rates, ingestion ≈ $0.00113/memory.
          A single retrieval (14k tokens saved at $3/1M) saves $0.042 —{" "}
          <span className="text-teal-400">37× the ingestion cost.</span>
        </p>
      </div>

      <p className="text-xs text-slate-600 mt-3">
        Token counts are averaged across all providers. Ingestion uses gpt-4o-mini pricing.
      </p>
    </div>
  );
}
