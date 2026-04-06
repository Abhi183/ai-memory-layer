"""
Gemini provider — wraps the `gemini` CLI or falls back to the
google-generativeai Python SDK.

Strategy:
  * If the `gemini` CLI binary is on PATH, delegate to it via subprocess
    (same pattern as the claude provider).
  * Otherwise use ``google.generativeai`` SDK directly with streaming.

Flow:
  1. Fetch augmented prompt from the memory API.
  2. Generate response via CLI or SDK.
  3. Stream output to the terminal.
  4. POST original prompt + full response to /memory/capture.
  5. Return the full response text.
"""

import shutil
import subprocess
import sys

from rich.console import Console

from mem_ai import client
from mem_ai.config import config

console = Console()

PROVIDER_NAME = "gemini"


def _has_gemini_cli() -> bool:
    return shutil.which("gemini") is not None


def _ask_via_cli(augmented_prompt: str) -> str:
    """Delegate to the `gemini` CLI subprocess and return stdout."""
    try:
        proc = subprocess.run(  # noqa: S603
            ["gemini", "-p", augmented_prompt],
            capture_output=False,
            stdout=subprocess.PIPE,
            stderr=sys.stderr,
            text=True,
        )
        return proc.stdout or ""
    except FileNotFoundError:
        console.print(
            "[bold red]Error:[/bold red] `gemini` CLI not found and "
            "google-generativeai SDK is also missing.",
            err=True,
        )
        sys.exit(1)


def _ask_via_sdk(augmented_prompt: str, model: str, stream: bool) -> str:
    """Use google-generativeai SDK with optional streaming."""
    try:
        import google.generativeai as genai  # noqa: PLC0415
    except ImportError:
        console.print(
            "[bold red]Error:[/bold red] google-generativeai package not installed. "
            "Run: pip install google-generativeai",
            err=True,
        )
        sys.exit(1)

    # GOOGLE_API_KEY must be set in the environment
    import os  # noqa: PLC0415

    api_key = os.environ.get("GOOGLE_API_KEY") or os.environ.get("GEMINI_API_KEY")
    if not api_key:
        console.print(
            "[bold red]Error:[/bold red] GOOGLE_API_KEY or GEMINI_API_KEY "
            "environment variable not set.",
            err=True,
        )
        sys.exit(1)

    genai.configure(api_key=api_key)
    model_obj = genai.GenerativeModel(model)

    response_parts: list[str] = []

    if stream:
        for chunk in model_obj.generate_content(augmented_prompt, stream=True):
            text = chunk.text if hasattr(chunk, "text") else ""
            if text:
                print(text, end="", flush=True)
                response_parts.append(text)
        print()
        return "".join(response_parts)
    else:
        result = model_obj.generate_content(augmented_prompt)
        text = result.text if hasattr(result, "text") else ""
        print(text)
        return text


def ask(
    prompt: str,
    model: str | None = None,
    platform: str = PROVIDER_NAME,
    stream: bool = True,
) -> str:
    """Ask Gemini with memory context injected.

    Parameters
    ----------
    prompt:
        The raw user prompt.
    model:
        Gemini model ID (defaults to config ``gemini_model``).
    platform:
        Platform label stored with the captured memory.
    stream:
        When True (SDK path only), tokens are printed incrementally.

    Returns
    -------
    str
        The AI response text.
    """
    model = model or config.gemini_model

    # 1. Fetch augmented prompt ------------------------------------------------
    context_data = client.get_context(prompt, platform=platform)
    augmented_prompt: str = context_data.get("augmented_prompt", prompt)
    injected: list = context_data.get("injected_memories", [])
    tokens_used: int = context_data.get("context_tokens_used", 0)

    if injected:
        console.print(
            f"[dim cyan]Retrieved {len(injected)} memories "
            f"({tokens_used} tokens)[/dim cyan]",
            err=True,
        )
    else:
        console.print("[dim]No relevant memories found.[/dim]", err=True)

    # 2. Generate response -----------------------------------------------------
    if _has_gemini_cli():
        # CLI path — always prints output itself via subprocess inheritance
        response = _ask_via_cli(augmented_prompt)
        print(response, end="")
    else:
        response = _ask_via_sdk(augmented_prompt, model=model, stream=stream)

    # 3. Capture interaction ---------------------------------------------------
    client.capture(prompt, response, platform=platform)

    return response
