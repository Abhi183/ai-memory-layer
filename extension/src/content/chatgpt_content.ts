/**
 * ChatGPT content script
 *
 * Responsibilities:
 *  1. Detect when the user submits a prompt.
 *  2. (Optional) Inject memory context into the prompt before sending.
 *  3. After the response is complete, capture prompt + response and send
 *     to the background service worker for storage.
 *
 * Detection strategy: MutationObserver on the conversation container.
 * ChatGPT renders new messages as DOM nodes — we watch for additions.
 */

import { captureMemory, getContext } from "../utils/api";

const PLATFORM = "chatgpt";
const SOURCE_URL = window.location.href;

// Track what we've already captured to avoid duplicates
const capturedMessageIds = new Set<string>();

// ── DOM helpers ────────────────────────────────────────────────────────────────

function getConversationTurns(): Array<{ role: string; text: string; id: string }> {
  const turns: Array<{ role: string; text: string; id: string }> = [];

  // ChatGPT uses [data-message-id] attributes on turn containers
  const nodes = document.querySelectorAll("[data-message-id]");
  nodes.forEach((node) => {
    const id = node.getAttribute("data-message-id") || "";
    const authorAttr = node.getAttribute("data-message-author-role") || "";
    const text = (node as HTMLElement).innerText?.trim() || "";
    if (text) {
      turns.push({ role: authorAttr, text, id });
    }
  });

  return turns;
}

function extractLastExchange(): { prompt: string; response: string } | null {
  const turns = getConversationTurns();
  // Walk backwards: find last assistant turn, then the user turn before it
  for (let i = turns.length - 1; i >= 0; i--) {
    if (turns[i].role === "assistant" && i > 0 && turns[i - 1].role === "user") {
      return { prompt: turns[i - 1].text, response: turns[i].text };
    }
  }
  return null;
}

// ── Context injection ─────────────────────────────────────────────────────────

async function injectContextIntoTextarea(textarea: HTMLTextAreaElement): Promise<void> {
  const currentText = textarea.value.trim();
  if (!currentText || currentText.length < 10) return;

  try {
    const ctx = await getContext({ prompt: currentText, platform: PLATFORM });
    if (ctx.injected_memories.length === 0) return;

    // Prepend context — user can see and edit it before sending
    const contextNote = ctx.injected_memories
      .map((m) => `[Memory] ${m.memory.summary || m.memory.content.slice(0, 150)}`)
      .join("\n");

    textarea.value = `${contextNote}\n\n${currentText}`;
    // Trigger React's synthetic event so the UI updates
    textarea.dispatchEvent(new Event("input", { bubbles: true }));
  } catch {
    // Context injection is best-effort, never block the user
  }
}

// ── Capture observer ──────────────────────────────────────────────────────────

let debounceTimer: ReturnType<typeof setTimeout> | null = null;

function onDOMChange() {
  if (debounceTimer) clearTimeout(debounceTimer);
  debounceTimer = setTimeout(async () => {
    const exchange = extractLastExchange();
    if (!exchange) return;

    // Create a stable ID from prompt hash to avoid double-captures
    const exchangeId = btoa(exchange.prompt.slice(0, 50)).replace(/=/g, "");
    if (capturedMessageIds.has(exchangeId)) return;

    // Only capture complete responses (heuristic: no streaming indicator)
    const isStreaming = !!document.querySelector("[data-is-streaming='true']");
    if (isStreaming) return;

    capturedMessageIds.add(exchangeId);

    try {
      await captureMemory({
        prompt: exchange.prompt,
        response: exchange.response,
        platform: PLATFORM,
        source_url: SOURCE_URL,
        session_id: extractSessionId(),
      });
    } catch (err) {
      // Silently fail — never interrupt the user's workflow
      console.debug("[AI Memory] Capture error:", err);
    }
  }, 1500); // Wait 1.5s after last DOM change to ensure response is complete
}

function extractSessionId(): string {
  // ChatGPT conversation IDs are in the URL: /c/{id}
  const match = window.location.pathname.match(/\/c\/([a-zA-Z0-9-]+)/);
  return match ? match[1] : "unknown";
}

// ── Initialization ─────────────────────────────────────────────────────────────

function init() {
  // Watch the full document body for new conversation turns
  const observer = new MutationObserver(onDOMChange);
  observer.observe(document.body, { childList: true, subtree: true });

  console.debug("[AI Memory] ChatGPT content script active");
}

if (document.readyState === "loading") {
  document.addEventListener("DOMContentLoaded", init);
} else {
  init();
}
