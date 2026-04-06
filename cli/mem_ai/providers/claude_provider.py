"""
Claude provider — wraps the `claude` CLI subprocess.

Flow:
  1. Fetch augmented prompt from the memory API.
  2. Execute `claude -p "<augmented_prompt>"` as a subprocess.
  3. Stream / capture stdout.
  4. POST the original prompt + AI response back to /memory/capture.
  5. Return the response text to the caller.
"""

import subprocess
import sys
from typing import Iterator

from rich.console import Console

from mem_ai import client
from mem_ai.config import config

console = Console()

PROVIDER_NAME = "claude"


def _run_claude(prompt: str) -> str:
    """Invoke the `claude` CLI and return its full stdout as a string.

    Falls back to streaming output directly to the terminal so the user
    sees progress in real time, then returns the accumulated text.
    """
    try:
        proc = subprocess.run(  # noqa: S603
            ["claude", "-p", prompt],
            capture_output=False,
            text=True,
            stdout=subprocess.PIPE,
            stderr=sys.stderr,
        )
        return proc.stdout or ""
    except FileNotFoundError:
        console.print(
            "[bold red]Error:[/bold red] `claude` CLI not found. "
            "Install it with: npm install -g @anthropic-ai/claude-code",
            err=True,
        )
        sys.exit(1)


def _stream_claude(prompt: str) -> Iterator[str]:
    """Stream `claude -p` output line-by-line."""
    try:
        with subprocess.Popen(  # noqa: S603
            ["claude", "-p", prompt],
            stdout=subprocess.PIPE,
            stderr=sys.stderr,
            text=True,
            bufsize=1,
        ) as proc:
            if proc.stdout is None:
                return
            for line in proc.stdout:
                yield line
    except FileNotFoundError:
        console.print(
            "[bold red]Error:[/bold red] `claude` CLI not found. "
            "Install it with: npm install -g @anthropic-ai/claude-code",
            err=True,
        )
        sys.exit(1)


def ask(
    prompt: str,
    platform: str = PROVIDER_NAME,
    stream: bool = True,
) -> str:
    """Ask Claude with memory context injected.

    Parameters
    ----------
    prompt:
        The raw user prompt.
    platform:
        Platform label stored with the captured memory (defaults to "claude").
    stream:
        When True, output is printed to stdout incrementally as it arrives.

    Returns
    -------
    str
        The AI response text.
    """
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

    # 2. Call claude CLI -------------------------------------------------------
    response_parts: list[str] = []

    if stream:
        for chunk in _stream_claude(augmented_prompt):
            print(chunk, end="", flush=True)
            response_parts.append(chunk)
        response = "".join(response_parts)
    else:
        response = _run_claude(augmented_prompt)
        print(response, end="")

    # 3. Capture interaction ---------------------------------------------------
    client.capture(prompt, response, platform=platform)

    return response
