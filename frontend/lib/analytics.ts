/**
 * Analytics API client for the Economics Dashboard.
 * Fetches cost savings, token metrics, and provider breakdowns.
 */

import { api } from "@/lib/api";

// ── Types ──────────────────────────────────────────────────────────────────

export interface AnalyticsSummary {
  total_cost_saved_usd: number;
  total_tokens_saved: number;
  avg_compression_ratio: number;
  memory_hit_rate: number;
  total_queries: number;
  total_memories_used: number;
  period_days: number;
  /** Percentage change vs previous period (positive = improvement) */
  cost_saved_trend_pct: number;
  tokens_saved_trend_pct: number;
  hit_rate_trend_pct: number;
  compression_trend_pct: number;
  avg_original_tokens: number;
  avg_memory_tokens: number;
  cost_per_million_tokens: number;
}

export interface TimelinePoint {
  date: string;           // ISO date string "2024-01-15"
  tokens_saved: number;
  cost_saved_usd: number;
  queries: number;
  hit_rate: number;
}

export interface ProviderStat {
  provider: string;
  total_tokens_saved: number;
  cost_saved_usd: number;
  request_count: number;
  avg_compression_ratio: number;
  hit_rate: number;
}

export interface AnalyticsResponse<T> {
  data: T;
  generated_at: string;
}

// ── Fallback mock data (shown when API has no data yet) ─────────────────────

export const MOCK_SUMMARY: AnalyticsSummary = {
  total_cost_saved_usd: 0,
  total_tokens_saved: 0,
  avg_compression_ratio: 0,
  memory_hit_rate: 0,
  total_queries: 0,
  total_memories_used: 0,
  period_days: 30,
  cost_saved_trend_pct: 0,
  tokens_saved_trend_pct: 0,
  hit_rate_trend_pct: 0,
  compression_trend_pct: 0,
  avg_original_tokens: 0,
  avg_memory_tokens: 0,
  cost_per_million_tokens: 3.0,
};

export const DEMO_SUMMARY: AnalyticsSummary = {
  total_cost_saved_usd: 47.83,
  total_tokens_saved: 15_943_200,
  avg_compression_ratio: 8.4,
  memory_hit_rate: 76.2,
  total_queries: 2847,
  total_memories_used: 2169,
  period_days: 30,
  cost_saved_trend_pct: 12.4,
  tokens_saved_trend_pct: 18.7,
  hit_rate_trend_pct: 4.1,
  compression_trend_pct: 2.3,
  avg_original_tokens: 14_800,
  avg_memory_tokens: 1_762,
  cost_per_million_tokens: 3.0,
};

export const DEMO_TIMELINE: TimelinePoint[] = Array.from({ length: 30 }, (_, i) => {
  const date = new Date();
  date.setDate(date.getDate() - (29 - i));
  const base = 400_000 + Math.sin(i / 4) * 120_000 + i * 8_000;
  const noise = (Math.random() - 0.5) * 80_000;
  const tokens = Math.max(0, Math.round(base + noise));
  return {
    date: date.toISOString().slice(0, 10),
    tokens_saved: tokens,
    cost_saved_usd: parseFloat((tokens * 3.0 / 1_000_000).toFixed(4)),
    queries: Math.round(tokens / 5_600),
    hit_rate: parseFloat((70 + Math.random() * 15).toFixed(1)),
  };
});

export const DEMO_PROVIDERS: ProviderStat[] = [
  {
    provider: "Claude",
    total_tokens_saved: 7_200_000,
    cost_saved_usd: 21.6,
    request_count: 1240,
    avg_compression_ratio: 9.1,
    hit_rate: 81.3,
  },
  {
    provider: "GPT-4",
    total_tokens_saved: 5_400_000,
    cost_saved_usd: 16.2,
    request_count: 890,
    avg_compression_ratio: 7.8,
    hit_rate: 73.4,
  },
  {
    provider: "Gemini",
    total_tokens_saved: 2_100_000,
    cost_saved_usd: 6.3,
    request_count: 512,
    avg_compression_ratio: 6.9,
    hit_rate: 69.8,
  },
  {
    provider: "Ollama",
    total_tokens_saved: 1_243_200,
    cost_saved_usd: 3.73,
    request_count: 205,
    avg_compression_ratio: 5.4,
    hit_rate: 62.1,
  },
];

// ── API functions ───────────────────────────────────────────────────────────

const BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000/api/v1";

async function fetchAnalytics<T>(path: string): Promise<T> {
  // Re-use the api client's auth token via its internal fetch.
  // We call the underlying endpoint directly since api.fetch is private.
  const token =
    typeof localStorage !== "undefined"
      ? localStorage.getItem("auth_token")
      : null;

  const res = await fetch(`${BASE}${path}`, {
    headers: {
      "Content-Type": "application/json",
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
    },
  });

  if (!res.ok) {
    throw new Error(`Analytics API error ${res.status}: ${res.statusText}`);
  }
  return res.json() as Promise<T>;
}

export async function getAnalyticsSummary(days = 30): Promise<AnalyticsSummary> {
  return fetchAnalytics<AnalyticsSummary>(`/analytics/summary?days=${days}`);
}

export async function getAnalyticsTimeline(days = 30): Promise<TimelinePoint[]> {
  return fetchAnalytics<TimelinePoint[]>(`/analytics/timeline?days=${days}`);
}

export async function getProviderBreakdown(): Promise<ProviderStat[]> {
  return fetchAnalytics<ProviderStat[]>("/analytics/providers");
}

// ── Formatting helpers ──────────────────────────────────────────────────────

export function formatUsd(value: number): string {
  if (value >= 1000) {
    return `$${(value / 1000).toFixed(1)}k`;
  }
  return `$${value.toFixed(2)}`;
}

export function formatTokens(value: number): string {
  if (value >= 1_000_000) {
    return `${(value / 1_000_000).toFixed(1)}M`;
  }
  if (value >= 1_000) {
    return `${(value / 1_000).toFixed(0)}k`;
  }
  return value.toLocaleString();
}

export function formatNumber(value: number): string {
  return value.toLocaleString();
}

export function formatPct(value: number): string {
  return `${value.toFixed(1)}%`;
}
