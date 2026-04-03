import { login, logout } from "../utils/api";

const $ = (id: string) => document.getElementById(id)!;

async function detectPlatform(): Promise<string> {
  const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
  const url = tab?.url || "";
  if (url.includes("chat.openai.com") || url.includes("chatgpt.com")) return "ChatGPT";
  if (url.includes("claude.ai")) return "Claude";
  if (url.includes("cursor.sh")) return "Cursor";
  if (url.includes("notion.so")) return "Notion AI";
  return "Unknown";
}

async function checkAuth(): Promise<boolean> {
  return new Promise((resolve) => {
    chrome.storage.local.get(["auth_token"], (r) => resolve(!!r.auth_token));
  });
}

async function init() {
  const authenticated = await checkAuth();

  if (authenticated) {
    showDashboard();
  } else {
    $("loginView").classList.remove("hidden");
    $("dashboardView").classList.add("hidden");
    $("statusDot").classList.remove("connected");
  }
}

async function showDashboard() {
  $("loginView").classList.add("hidden");
  $("dashboardView").classList.remove("hidden");
  $("statusDot").classList.add("connected");

  const platform = await detectPlatform();
  $("currentPlatform").textContent = platform;
}

function showMessage(id: string, text: string, type: "error" | "success") {
  const el = $(id);
  el.textContent = text;
  el.className = `message ${type}`;
  el.classList.remove("hidden");
}

$("loginBtn").addEventListener("click", async () => {
  const email = ($("emailInput") as HTMLInputElement).value.trim();
  const password = ($("passwordInput") as HTMLInputElement).value;

  if (!email || !password) {
    showMessage("loginMessage", "Please enter email and password.", "error");
    return;
  }

  $("loginBtn").textContent = "Signing in…";
  ($("loginBtn") as HTMLButtonElement).disabled = true;

  try {
    await login(email, password);
    showMessage("loginMessage", "Signed in successfully!", "success");
    setTimeout(showDashboard, 800);
  } catch (err) {
    showMessage("loginMessage", "Invalid credentials. Please try again.", "error");
  } finally {
    $("loginBtn").textContent = "Sign In";
    ($("loginBtn") as HTMLButtonElement).disabled = false;
  }
});

$("logoutBtn").addEventListener("click", async () => {
  await logout();
  $("dashboardView").classList.add("hidden");
  $("loginView").classList.remove("hidden");
  $("statusDot").classList.remove("connected");
});

$("openDashboardBtn").addEventListener("click", () => {
  chrome.tabs.create({ url: "http://localhost:3000" });
});

init();
