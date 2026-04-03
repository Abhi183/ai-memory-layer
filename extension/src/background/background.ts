/**
 * Background service worker (Manifest V3).
 *
 * Responsibilities:
 *  - Relay messages from content scripts to the memory API.
 *  - Manage authentication state.
 *  - Periodic sync: push any queued (offline) captures when back online.
 *  - Badge updates to indicate memory count / sync status.
 */

import { captureMemory, CapturePayload } from "../utils/api";

// ── Offline queue ─────────────────────────────────────────────────────────────

interface QueuedCapture {
  payload: CapturePayload;
  timestamp: number;
  retries: number;
}

async function getQueue(): Promise<QueuedCapture[]> {
  return new Promise((resolve) => {
    chrome.storage.local.get(["offline_queue"], (r) => {
      resolve(r.offline_queue || []);
    });
  });
}

async function saveQueue(queue: QueuedCapture[]): Promise<void> {
  await chrome.storage.local.set({ offline_queue: queue });
}

async function enqueueCapture(payload: CapturePayload): Promise<void> {
  const queue = await getQueue();
  queue.push({ payload, timestamp: Date.now(), retries: 0 });
  // Keep at most 100 queued captures
  if (queue.length > 100) queue.shift();
  await saveQueue(queue);
}

async function flushQueue(): Promise<void> {
  const queue = await getQueue();
  if (queue.length === 0) return;

  const remaining: QueuedCapture[] = [];

  for (const item of queue) {
    try {
      await captureMemory(item.payload);
    } catch {
      if (item.retries < 3) {
        remaining.push({ ...item, retries: item.retries + 1 });
      }
      // Drop after 3 retries
    }
  }

  await saveQueue(remaining);
}

// ── Message handling ──────────────────────────────────────────────────────────

chrome.runtime.onMessage.addListener((message, _sender, sendResponse) => {
  if (message.type === "CAPTURE_MEMORY") {
    handleCapture(message.payload).then(() => sendResponse({ success: true })).catch((err) => {
      sendResponse({ success: false, error: err.message });
    });
    return true; // Keep channel open for async response
  }

  if (message.type === "GET_STATUS") {
    chrome.storage.local.get(["auth_token"], (r) => {
      sendResponse({ authenticated: !!r.auth_token });
    });
    return true;
  }
});

async function handleCapture(payload: CapturePayload): Promise<void> {
  try {
    await captureMemory(payload);
    await updateBadge("+1");
  } catch {
    // Offline or error — queue for later
    await enqueueCapture(payload);
    await updateBadge("Q");
  }
}

// ── Badge ─────────────────────────────────────────────────────────────────────

async function updateBadge(text: string): Promise<void> {
  chrome.action.setBadgeText({ text });
  chrome.action.setBadgeBackgroundColor({ color: text === "Q" ? "#F59E0B" : "#10B981" });
  // Clear badge after 3 seconds
  setTimeout(() => chrome.action.setBadgeText({ text: "" }), 3000);
}

// ── Periodic queue flush ───────────────────────────────────────────────────────

chrome.alarms.create("flush_queue", { periodInMinutes: 5 });
chrome.alarms.onAlarm.addListener((alarm) => {
  if (alarm.name === "flush_queue") {
    flushQueue();
  }
});

// Flush on startup
chrome.runtime.onStartup.addListener(flushQueue);
chrome.runtime.onInstalled.addListener(flushQueue);

console.debug("[AI Memory] Background service worker initialized");
