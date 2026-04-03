/**
 * Claude.ai content script
 * Mirrors the ChatGPT content script but adapted for Claude's DOM structure.
 */

import { captureMemory } from "../utils/api";

const PLATFORM = "claude";
const capturedIds = new Set<string>();

function extractLastExchange(): { prompt: string; response: string } | null {
  // Claude renders user messages with [data-testid="human-turn"]
  // and assistant messages with [data-testid="ai-turn"]
  const humanTurns = Array.from(document.querySelectorAll('[data-testid="human-turn"]'));
  const aiTurns = Array.from(document.querySelectorAll('[data-testid="ai-turn"]'));

  if (humanTurns.length === 0 || aiTurns.length === 0) return null;

  const lastHuman = humanTurns[humanTurns.length - 1] as HTMLElement;
  const lastAI = aiTurns[aiTurns.length - 1] as HTMLElement;

  const prompt = lastHuman.innerText?.trim() || "";
  const response = lastAI.innerText?.trim() || "";

  return prompt && response ? { prompt, response } : null;
}

let debounce: ReturnType<typeof setTimeout> | null = null;

function onDOMChange() {
  if (debounce) clearTimeout(debounce);
  debounce = setTimeout(async () => {
    // Check if Claude is still generating
    const isGenerating = !!document.querySelector('[data-testid="stop-button"]');
    if (isGenerating) return;

    const exchange = extractLastExchange();
    if (!exchange) return;

    const id = btoa(exchange.prompt.slice(0, 50)).replace(/=/g, "");
    if (capturedIds.has(id)) return;
    capturedIds.add(id);

    try {
      await captureMemory({
        prompt: exchange.prompt,
        response: exchange.response,
        platform: PLATFORM,
        source_url: window.location.href,
        session_id: window.location.pathname.split("/").pop() || "unknown",
      });
    } catch (err) {
      console.debug("[AI Memory] Claude capture error:", err);
    }
  }, 1500);
}

const observer = new MutationObserver(onDOMChange);
observer.observe(document.body, { childList: true, subtree: true });
console.debug("[AI Memory] Claude content script active");
