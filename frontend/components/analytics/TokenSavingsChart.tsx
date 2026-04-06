"use client";

import {
  AreaChart,
  Area,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  Legend,
} from "recharts";
import { format, parseISO } from "date-fns";
import { TimelinePoint } from "@/lib/analytics";

interface Props {
  data: TimelinePoint[];
}

function formatTokenAxis(value: number): string {
  if (value >= 1_000_000) return `${(value / 1_000_000).toFixed(1)}M`;
  if (value >= 1_000) return `${(value / 1_000).toFixed(0)}k`;
  return String(value);
}

function formatUsdAxis(value: number): string {
  return `$${value.toFixed(2)}`;
}

interface TooltipPayload {
  name: string;
  value: number;
  color: string;
}

interface CustomTooltipProps {
  active?: boolean;
  payload?: TooltipPayload[];
  label?: string;
}

function CustomTooltip({ active, payload, label }: CustomTooltipProps) {
  if (!active || !payload?.length) return null;

  const tokensEntry = payload.find((p) => p.name === "Tokens Saved");
  const costEntry = payload.find((p) => p.name === "Cost Saved (USD)");

  return (
    <div className="bg-slate-800 border border-slate-700 rounded-xl px-4 py-3 shadow-2xl text-sm">
      <p className="text-slate-300 font-medium mb-2">
        {label ? format(parseISO(label), "MMM d, yyyy") : ""}
      </p>
      {tokensEntry && (
        <div className="flex items-center gap-2 text-violet-300">
          <span className="w-2 h-2 rounded-full bg-violet-400 inline-block" />
          <span className="text-slate-400">Tokens saved:</span>
          <span className="font-semibold">{tokensEntry.value.toLocaleString()}</span>
        </div>
      )}
      {costEntry && (
        <div className="flex items-center gap-2 text-emerald-300 mt-1">
          <span className="w-2 h-2 rounded-full bg-emerald-400 inline-block" />
          <span className="text-slate-400">Cost saved:</span>
          <span className="font-semibold">${costEntry.value.toFixed(4)}</span>
        </div>
      )}
    </div>
  );
}

export default function TokenSavingsChart({ data }: Props) {
  if (!data.length) {
    return (
      <div className="bg-slate-900 border border-slate-800 rounded-2xl p-6 flex items-center justify-center h-64 text-slate-500 text-sm">
        No timeline data yet.
      </div>
    );
  }

  const tickInterval = Math.max(1, Math.floor(data.length / 6));

  return (
    <div className="bg-slate-900 border border-slate-800 rounded-2xl p-5">
      <div className="flex items-center justify-between mb-5">
        <div>
          <h2 className="text-base font-semibold text-white">Token Savings Over Time</h2>
          <p className="text-xs text-slate-500 mt-0.5">Daily tokens and cost saved via memory injection</p>
        </div>
        <span className="text-xs text-slate-500 bg-slate-800 px-2.5 py-1 rounded-full">
          Last {data.length}d
        </span>
      </div>

      <ResponsiveContainer width="100%" height={240}>
        <AreaChart data={data} margin={{ top: 4, right: 16, left: 0, bottom: 0 }}>
          <defs>
            <linearGradient id="gradTokens" x1="0" y1="0" x2="0" y2="1">
              <stop offset="5%" stopColor="#7c3aed" stopOpacity={0.4} />
              <stop offset="95%" stopColor="#7c3aed" stopOpacity={0.02} />
            </linearGradient>
            <linearGradient id="gradCost" x1="0" y1="0" x2="0" y2="1">
              <stop offset="5%" stopColor="#10b981" stopOpacity={0.35} />
              <stop offset="95%" stopColor="#10b981" stopOpacity={0.02} />
            </linearGradient>
          </defs>

          <CartesianGrid strokeDasharray="3 3" stroke="#1e293b" vertical={false} />

          <XAxis
            dataKey="date"
            tick={{ fill: "#64748b", fontSize: 11 }}
            axisLine={false}
            tickLine={false}
            interval={tickInterval}
            tickFormatter={(v) => format(parseISO(v as string), "MMM d")}
          />

          {/* Left Y: tokens */}
          <YAxis
            yAxisId="tokens"
            orientation="left"
            tick={{ fill: "#7c3aed", fontSize: 11 }}
            axisLine={false}
            tickLine={false}
            tickFormatter={formatTokenAxis}
            width={48}
          />

          {/* Right Y: cost */}
          <YAxis
            yAxisId="cost"
            orientation="right"
            tick={{ fill: "#10b981", fontSize: 11 }}
            axisLine={false}
            tickLine={false}
            tickFormatter={formatUsdAxis}
            width={52}
          />

          <Tooltip content={<CustomTooltip />} />

          <Legend
            wrapperStyle={{ fontSize: 12, color: "#94a3b8", paddingTop: 12 }}
            formatter={(value) => (
              <span style={{ color: "#94a3b8" }}>{value}</span>
            )}
          />

          <Area
            yAxisId="tokens"
            type="monotone"
            dataKey="tokens_saved"
            name="Tokens Saved"
            stroke="#7c3aed"
            strokeWidth={2}
            fill="url(#gradTokens)"
            dot={false}
            activeDot={{ r: 4, fill: "#7c3aed", strokeWidth: 0 }}
          />

          <Area
            yAxisId="cost"
            type="monotone"
            dataKey="cost_saved_usd"
            name="Cost Saved (USD)"
            stroke="#10b981"
            strokeWidth={2}
            fill="url(#gradCost)"
            dot={false}
            activeDot={{ r: 4, fill: "#10b981", strokeWidth: 0 }}
          />
        </AreaChart>
      </ResponsiveContainer>
    </div>
  );
}
