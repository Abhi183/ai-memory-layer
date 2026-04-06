"""
OpenAI provider — calls the OpenAI Python SDK directly.

Flow:
  1. Fetch augmented prompt from the memory API.
  2. Call openai.chat.completions.create() with streaming enabled.
  3. Stream tokens to the terminal.
  4. POST original prompt + full response to /memory/capture.
  5. Return the full response text.
"""

import sys

from rich.console import Console

from mem_ai import client
from mem_ai.config import config

console = Console()

PROVIDER_NAME = "openai"


def ask(
    prompt: str,
    model: str | None = None,
    platform: str = PROVIDER_NAME,
    stream: bool = True,
) -> str:
    """Ask OpenAI with memory context injected.

    Parameters
    ----------
    prompt:
        The raw user prompt.
    model:
        OpenAI model ID (defaults to config ``openai_model``).
    platform:
        Platform label stored with the captured memory.
    stream:
        When True, tokens are printed incrementally to stdout.

    Returns
    -------
    str
        The AI response text.
    """
    try:
        import openai  # noqa: PLC0415
    except ImportError:
        console.print(
            "[bold red]Error:[/bold red] openai package not installed. "
            "Run: pip install openai",
            err=True,
        )
        sys.exit(1)

    model = model or config.openai_model

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

    # 2. Call OpenAI SDK -------------------------------------------------------
    openai_client = openai.OpenAI()  # reads OPENAI_API_KEY from env
    messages = [{"role": "user", "content": augmented_prompt}]

    response_parts: list[str] = []

    if stream:
        with openai_client.chat.completions.create(
            model=model,
            messages=messages,
            stream=True,
        ) as stream_resp:
            for chunk in stream_resp:
                delta = chunk.choices[0].delta
                text = delta.content or ""
                if text:
                    print(text, end="", flush=True)
                    response_parts.append(text)
        print()  # newline after streaming ends
        response = "".join(response_parts)
    else:
        completion = openai_client.chat.completions.create(
            model=model,
            messages=messages,
        )
        response = completion.choices[0].message.content or ""
        print(response)

    # 3. Capture interaction ---------------------------------------------------
    client.capture(prompt, response, platform=platform)

    return response
