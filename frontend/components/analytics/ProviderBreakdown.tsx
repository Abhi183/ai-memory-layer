"use client";

import { ProviderStat, formatUsd, formatTokens, formatPct } from "@/lib/analytics";

interface Props {
  providers: ProviderStat[];
}

const PROVIDER_COLORS: Record<string, { bar: string; badge: string }> = {
  Claude:   { bar: "bg-violet-500",  badge: "bg-violet-900/60 text-violet-300 border-violet-700/50" },
  "GPT-4":  { bar: "bg-sky-500",     badge: "bg-sky-900/60 text-sky-300 border-sky-700/50" },
  Gemini:   { bar: "bg-blue-500",    badge: "bg-blue-900/60 text-blue-300 border-blue-700/50" },
  Ollama:   { bar: "bg-emerald-500", badge: "bg-emerald-900/60 text-emerald-300 border-emerald-700/50" },
};

function getColor(provider: string) {
  return PROVIDER_COLORS[provider] ?? { bar: "bg-indigo-500", badge: "bg-indigo-900/60 text-indigo-300 border-indigo-700/50" };
}

function initials(provider: string): string {
  return provider.slice(0, 2).toUpperCase();
}

export default function ProviderBreakdown({ providers }: Props) {
  if (!providers.length) {
    return (
      <div className="bg-slate-900 border border-slate-800 rounded-2xl p-6 flex items-center justify-center h-48 text-slate-500 text-sm">
        No provider data yet.
      </div>
    );
  }

  const maxTokens = Math.max(...providers.map((p) => p.total_tokens_saved));

  return (
    <div className="bg-slate-900 border border-slate-800 rounded-2xl p-5">
      <div className="mb-5">
        <h2 className="text-base font-semibold text-white">Provider Breakdown</h2>
        <p className="text-xs text-slate-500 mt-0.5">Savings attributed to each AI provider</p>
      </div>

      {/* Table header */}
      <div className="hidden sm:grid grid-cols-5 gap-3 text-xs font-medium text-slate-500 uppercase tracking-wider pb-2 border-b border-slate-800 mb-3">
        <span className="col-span-2">Provider</span>
        <span className="text-right">Tokens Saved</span>
        <span className="text-right">Cost Saved</span>
        <span className="text-right">Requests</span>
      </div>

      <div className="space-y-4">
        {providers.map((p) => {
          const color = getColor(p.provider);
          const barWidth =
            maxTokens > 0
              ? Math.max(4, Math.round((p.total_tokens_saved / maxTokens) * 100))
              : 4;

          return (
            <div key={p.provider} className="group">
              {/* Mobile layout */}
              <div className="sm:hidden space-y-2">
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-2.5">
                    <div
                      className={`w-8 h-8 rounded-lg flex items-center justify-center text-xs font-bold text-white ${color.bar}`}
                    >
                      {initials(p.provider)}
                    </div>
                    <span className="text-sm font-medium text-white">{p.provider}</span>
                  </div>
                  <span className={`text-xs px-2 py-0.5 rounded-full border ${color.badge}`}>
                    {formatPct(p.hit_rate)} hit
                  </span>
                </div>
                <div className="w-full bg-slate-800 rounded-full h-1.5">
                  <div
                    className={`h-1.5 rounded-full transition-all ${color.bar}`}
                    style={{ width: `${barWidth}%` }}
                  />
                </div>
                <div className="flex justify-between text-xs text-slate-400">
                  <span>{formatTokens(p.total_tokens_saved)} tokens</span>
                  <span className="text-emerald-400 font-medium">{formatUsd(p.cost_saved_usd)} saved</span>
                  <span>{p.request_count.toLocaleString()} req</span>
                </div>
              </div>

              {/* Desktop layout */}
              <div className="hidden sm:grid grid-cols-5 gap-3 items-center">
                {/* Provider name + bar */}
                <div className="col-span-2 space-y-1.5">
                  <div className="flex items-center gap-2.5">
                    <div
                      className={`w-7 h-7 rounded-lg flex items-center justify-center text-xs font-bold text-white shrink-0 ${color.bar}`}
                    >
                      {initials(p.provider)}
                    </div>
                    <span className="text-sm font-medium text-white">{p.provider}</span>
                    <span className={`text-xs px-2 py-0.5 rounded-full border ml-auto ${color.badge}`}>
                      {formatPct(p.hit_rate)} hit
                    </span>
                  </div>
                  <div className="w-full bg-slate-800 rounded-full h-1">
                    <div
                      className={`h-1 rounded-full transition-all duration-500 ${color.bar}`}
                      style={{ width: `${barWidth}%` }}
                    />
                  </div>
                </div>

                <span className="text-right text-sm text-slate-200">
                  {formatTokens(p.total_tokens_saved)}
                </span>
                <span className="text-right text-sm text-emerald-400 font-medium">
                  {formatUsd(p.cost_saved_usd)}
                </span>
                <span className="text-right text-sm text-slate-300">
                  {p.request_count.toLocaleString()}
                </span>
              </div>
            </div>
          );
        })}
      </div>

      {/* Summary footer */}
      <div className="mt-5 pt-4 border-t border-slate-800 grid grid-cols-3 gap-3 text-center">
        <div>
          <p className="text-lg font-bold text-white">
            {formatTokens(providers.reduce((s, p) => s + p.total_tokens_saved, 0))}
          </p>
          <p className="text-xs text-slate-500 mt-0.5">Total tokens</p>
        </div>
        <div>
          <p className="text-lg font-bold text-emerald-400">
            {formatUsd(providers.reduce((s, p) => s + p.cost_saved_usd, 0))}
          </p>
          <p className="text-xs text-slate-500 mt-0.5">Total saved</p>
        </div>
        <div>
          <p className="text-lg font-bold text-white">
            {providers.reduce((s, p) => s + p.request_count, 0).toLocaleString()}
          </p>
          <p className="text-xs text-slate-500 mt-0.5">Requests</p>
        </div>
      </div>
    </div>
  );
}
