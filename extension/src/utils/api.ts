/**
 * API client for communicating with the local AI Memory Layer backend.
 */

const DEFAULT_API_BASE = "http://localhost:8000/api/v1";

export interface CapturePayload {
  prompt: string;
  response: string;
  platform: string;
  source_url?: string;
  session_id?: string;
  tags?: string[];
}

export interface ContextPayload {
  prompt: string;
  platform?: string;
  max_tokens?: number;
  max_memories?: number;
}

export interface ContextResponse {
  original_prompt: string;
  augmented_prompt: string;
  injected_memories: Array<{
    memory: { content: string; summary?: string };
    similarity_score: number;
    relevance_rank: number;
  }>;
  context_tokens_used: number;
}

async function getAuthToken(): Promise<string | null> {
  return new Promise((resolve) => {
    chrome.storage.local.get(["auth_token"], (result) => {
      resolve(result.auth_token || null);
    });
  });
}

async function getApiBase(): Promise<string> {
  return new Promise((resolve) => {
    chrome.storage.local.get(["api_base"], (result) => {
      resolve(result.api_base || DEFAULT_API_BASE);
    });
  });
}

async function apiFetch(
  path: string,
  options: RequestInit = {}
): Promise<Response> {
  const [token, base] = await Promise.all([getAuthToken(), getApiBase()]);

  if (!token) {
    throw new Error("Not authenticated. Please log in via the extension popup.");
  }

  return fetch(`${base}${path}`, {
    ...options,
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${token}`,
      ...(options.headers || {}),
    },
  });
}

export async function captureMemory(payload: CapturePayload): Promise<void> {
  const res = await apiFetch("/memory/capture", {
    method: "POST",
    body: JSON.stringify(payload),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(`Capture failed: ${err.detail}`);
  }
}

export async function getContext(
  payload: ContextPayload
): Promise<ContextResponse> {
  const res = await apiFetch("/memory/context", {
    method: "POST",
    body: JSON.stringify(payload),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(`Context fetch failed: ${err.detail}`);
  }
  return res.json();
}

export async function login(
  email: string,
  password: string
): Promise<{ access_token: string }> {
  const base = await getApiBase();
  const res = await fetch(`${base}/auth/login`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ email, password }),
  });
  if (!res.ok) throw new Error("Login failed");
  const data = await res.json();
  await chrome.storage.local.set({ auth_token: data.access_token });
  return data;
}

export async function logout(): Promise<void> {
  await chrome.storage.local.remove(["auth_token"]);
}
