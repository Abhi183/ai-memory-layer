"""
Ollama provider — wraps `ollama run <model>` subprocess or calls the
Ollama REST API at http://localhost:11434.

Strategy:
  * Prefer the REST API (streaming JSON) for clean output handling.
  * Fall back to `ollama run <model>` subprocess if the API is unreachable.

Flow:
  1. Fetch augmented prompt from the memory API.
  2. Stream the response from Ollama.
  3. POST original prompt + full response to /memory/capture.
  4. Return the full response text.
"""

import json
import shutil
import subprocess
import sys
from typing import Iterator

import httpx
from rich.console import Console

from mem_ai import client
from mem_ai.config import config

console = Console()

PROVIDER_NAME = "ollama"
_OLLAMA_TIMEOUT = httpx.Timeout(120.0, connect=5.0)


def _stream_via_api(
    prompt: str,
    model: str,
    host: str,
) -> Iterator[str]:
    """Yield text tokens from the Ollama /api/generate streaming endpoint."""
    url = f"{host.rstrip('/')}/api/generate"
    payload = {"model": model, "prompt": prompt, "stream": True}

    with httpx.stream(
        "POST",
        url,
        json=payload,
        timeout=_OLLAMA_TIMEOUT,
    ) as resp:
        resp.raise_for_status()
        for raw_line in resp.iter_lines():
            if not raw_line:
                continue
            try:
                data = json.loads(raw_line)
            except json.JSONDecodeError:
                continue
            token = data.get("response", "")
            if token:
                yield token
            if data.get("done"):
                break


def _ask_via_subprocess(prompt: str, model: str) -> str:
    """Fall back to `ollama run <model>` via subprocess."""
    if not shutil.which("ollama"):
        console.print(
            "[bold red]Error:[/bold red] `ollama` not found and the Ollama API is "
            "unreachable. Install Ollama from https://ollama.ai",
            err=True,
        )
        sys.exit(1)

    try:
        proc = subprocess.run(  # noqa: S603
            ["ollama", "run", model],
            input=prompt,
            stdout=subprocess.PIPE,
            stderr=sys.stderr,
            text=True,
        )
        return proc.stdout or ""
    except FileNotFoundError:
        console.print(
            "[bold red]Error:[/bold red] `ollama` binary not found.",
            err=True,
        )
        sys.exit(1)


def ask(
    prompt: str,
    model: str | None = None,
    platform: str = PROVIDER_NAME,
    stream: bool = True,
) -> str:
    """Ask an Ollama model with memory context injected.

    Parameters
    ----------
    prompt:
        The raw user prompt.
    model:
        Ollama model name (defaults to config ``ollama_model``).
    platform:
        Platform label stored with the captured memory.
    stream:
        When True (API path), tokens are printed incrementally.

    Returns
    -------
    str
        The AI response text.
    """
    model = model or config.ollama_model
    host = config.ollama_host

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

    # 2. Generate response via REST API or subprocess --------------------------
    response_parts: list[str] = []

    try:
        for token in _stream_via_api(augmented_prompt, model=model, host=host):
            if stream:
                print(token, end="", flush=True)
            response_parts.append(token)
        if stream:
            print()  # final newline
        response = "".join(response_parts)
        if not stream:
            print(response)
    except (httpx.ConnectError, httpx.ReadTimeout):
        console.print(
            f"[yellow]Ollama API not reachable at {host}. "
            "Falling back to subprocess...[/yellow]",
            err=True,
        )
        response = _ask_via_subprocess(augmented_prompt, model=model)
        print(response, end="")

    # 3. Capture interaction ---------------------------------------------------
    client.capture(prompt, response, platform=platform)

    return response
