/**
 * Typed API client for the AI Memory Layer backend.
 * Used by the Next.js dashboard.
 */

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000/api/v1";

export type MemoryType = "short_term" | "long_term" | "semantic";
export type MemoryStatus = "pending" | "processing" | "active" | "archived" | "failed";

export interface Tag {
  id: string;
  name: string;
  color?: string;
}

export interface Source {
  id: string;
  platform: string;
  source_url?: string;
  session_id?: string;
  created_at: string;
}

export interface Memory {
  id: string;
  content: string;
  summary?: string;
  extracted_facts?: { facts: string[] };
  memory_type: MemoryType;
  status: MemoryStatus;
  source_platform?: string;
  importance_score: number;
  access_count: number;
  tags: Tag[];
  source?: Source;
  captured_at: string;
  processed_at?: string;
}

export interface MemorySearchResult {
  memory: Memory;
  similarity_score: number;
  relevance_rank: number;
}

export interface ContextResponse {
  original_prompt: string;
  augmented_prompt: string;
  injected_memories: MemorySearchResult[];
  context_tokens_used: number;
}

class ApiClient {
  private token: string | null = null;

  setToken(token: string) {
    this.token = token;
    if (typeof localStorage !== "undefined") {
      localStorage.setItem("auth_token", token);
    }
  }

  loadToken() {
    if (typeof localStorage !== "undefined") {
      this.token = localStorage.getItem("auth_token");
    }
  }

  clearToken() {
    this.token = null;
    if (typeof localStorage !== "undefined") {
      localStorage.removeItem("auth_token");
    }
  }

  isAuthenticated(): boolean {
    this.loadToken();
    return !!this.token;
  }

  private async fetch<T>(path: string, init: RequestInit = {}): Promise<T> {
    this.loadToken();
    const headers: Record<string, string> = {
      "Content-Type": "application/json",
    };
    if (this.token) headers["Authorization"] = `Bearer ${this.token}`;

    const res = await fetch(`${API_BASE}${path}`, { ...init, headers: { ...headers, ...(init.headers as Record<string, string> || {}) } });

    if (res.status === 401) {
      this.clearToken();
      throw new Error("Session expired. Please log in again.");
    }
    if (!res.ok) {
      const err = await res.json().catch(() => ({ detail: res.statusText }));
      throw new Error(err.detail || "Request failed");
    }
    if (res.status === 204) return undefined as T;
    return res.json();
  }

  // ── Auth ───────────────────────────────────────────────────────────────────
  async login(email: string, password: string): Promise<{ access_token: string }> {
    const data = await this.fetch<{ access_token: string }>("/auth/login", {
      method: "POST",
      body: JSON.stringify({ email, password }),
    });
    this.setToken(data.access_token);
    return data;
  }

  async register(email: string, username: string, password: string) {
    return this.fetch("/auth/register", {
      method: "POST",
      body: JSON.stringify({ email, username, password }),
    });
  }

  // ── Memories ───────────────────────────────────────────────────────────────
  async listMemories(params?: {
    memory_type?: MemoryType;
    platform?: string;
    limit?: number;
    offset?: number;
  }): Promise<Memory[]> {
    const qs = new URLSearchParams();
    if (params?.memory_type) qs.set("memory_type", params.memory_type);
    if (params?.platform) qs.set("platform", params.platform);
    if (params?.limit) qs.set("limit", String(params.limit));
    if (params?.offset) qs.set("offset", String(params.offset));
    return this.fetch(`/memory/?${qs}`);
  }

  async searchMemories(query: string, limit = 10): Promise<MemorySearchResult[]> {
    const qs = new URLSearchParams({ q: query, limit: String(limit) });
    return this.fetch(`/memory/search?${qs}`);
  }

  async createMemory(data: { content: string; memory_type?: MemoryType; tags?: string[] }): Promise<Memory> {
    return this.fetch("/memory/", { method: "POST", body: JSON.stringify(data) });
  }

  async deleteMemory(id: string): Promise<void> {
    return this.fetch(`/memory/${id}`, { method: "DELETE" });
  }

  async getContext(prompt: string): Promise<ContextResponse> {
    return this.fetch("/memory/context", {
      method: "POST",
      body: JSON.stringify({ prompt, max_memories: 5 }),
    });
  }
}

export const api = new ApiClient();
