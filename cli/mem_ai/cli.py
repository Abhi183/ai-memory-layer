"""
mem-ai: Universal AI CLI wrapper with persistent memory.

Entry point for the `mem-ai` command installed by setup.py.
"""

from __future__ import annotations

import getpass
import os
import sys
from typing import Optional

import click
from rich.columns import Columns
from rich.console import Console
from rich.panel import Panel
from rich.prompt import Prompt
from rich.table import Table
from rich import box

from mem_ai import client
from mem_ai.config import CONFIG_DIR, config
from mem_ai.providers import PROVIDERS

console = Console()

# ---------------------------------------------------------------------------
# Root group
# ---------------------------------------------------------------------------


@click.group()
@click.version_option(package_name="mem-ai")
def cli() -> None:
    """mem-ai — Universal AI CLI with persistent memory.

    Wraps any AI provider (claude, openai, gemini, ollama) and automatically
    injects relevant memories from your history before every prompt.
    """


# ---------------------------------------------------------------------------
# ask
# ---------------------------------------------------------------------------


@cli.command()
@click.argument("prompt")
@click.option(
    "--provider",
    "-p",
    default=None,
    show_default=True,
    help="AI provider: claude | openai | gemini | ollama",
)
@click.option(
    "--model",
    "-m",
    default=None,
    help="Model override (e.g. gpt-4o, gemini-1.5-pro, llama3).",
)
@click.option(
    "--platform",
    default=None,
    help="Platform label stored in memory (defaults to provider name).",
)
@click.option(
    "--no-stream",
    is_flag=True,
    default=False,
    help="Disable streaming output.",
)
def ask(
    prompt: str,
    provider: Optional[str],
    model: Optional[str],
    platform: Optional[str],
    no_stream: bool,
) -> None:
    """Ask an AI question with automatic memory injection.

    Examples:\n
      mem-ai ask "How do I fix this React bug?" --provider claude\n
      mem-ai ask "Summarize my project status" --provider openai --model gpt-4o\n
      mem-ai ask "Write tests for this function" --provider gemini
    """
    provider = provider or config.default_provider
    platform = platform or provider

    if provider not in PROVIDERS:
        console.print(
            f"[bold red]Unknown provider:[/bold red] {provider!r}. "
            f"Available: {', '.join(PROVIDERS)}",
            err=True,
        )
        sys.exit(1)

    kwargs: dict = {"prompt": prompt, "platform": platform, "stream": not no_stream}
    if model:
        kwargs["model"] = model

    PROVIDERS[provider].ask(**kwargs)


# ---------------------------------------------------------------------------
# capture
# ---------------------------------------------------------------------------


@cli.command()
@click.argument("prompt")
@click.argument("response")
@click.option(
    "--platform",
    default=None,
    help="Platform label (e.g. claude, cursor). Defaults to 'cli'.",
)
def capture(prompt: str, response: str, platform: Optional[str]) -> None:
    """Manually capture a prompt/response pair into memory.

    Example:\n
      mem-ai capture "What is PBKDF2?" "PBKDF2 is a key derivation function..." --platform claude
    """
    platform = platform or config.platform
    client.capture(prompt, response, platform=platform)
    console.print("[green]Captured.[/green]")


# ---------------------------------------------------------------------------
# search
# ---------------------------------------------------------------------------


@cli.command()
@click.argument("query")
@click.option("--limit", "-n", default=5, show_default=True, help="Number of results.")
def search(query: str, limit: int) -> None:
    """Semantic search over your stored memories.

    Example:\n
      mem-ai search "React hooks" --limit 5
    """
    results = client.search(query, limit=limit)

    if not results:
        console.print("[yellow]No memories found for that query.[/yellow]")
        return

    table = Table(
        title=f'Search results for "{query}"',
        box=box.ROUNDED,
        show_lines=True,
        highlight=True,
    )
    table.add_column("#", style="dim", width=4)
    table.add_column("Summary", style="white", max_width=60)
    table.add_column("Platform", style="cyan", width=14)
    table.add_column("Score", style="green", width=8)
    table.add_column("Date", style="dim", width=12)

    for i, mem in enumerate(results, 1):
        summary = mem.get("summary") or mem.get("content", "")[:120]
        platform_label = mem.get("source_platform", "—")
        score = mem.get("score") or mem.get("similarity_score")
        score_str = f"{score:.2f}" if score is not None else "—"
        date = ""
        captured_at = mem.get("captured_at", "")
        if captured_at:
            date = captured_at[:10]
        table.add_row(str(i), summary, platform_label, score_str, date)

    console.print(table)


# ---------------------------------------------------------------------------
# stats
# ---------------------------------------------------------------------------


@cli.command()
def stats() -> None:
    """Show the memory economics dashboard.

    Displays total tokens saved, cost savings, compression ratio, and
    the breakdown by AI provider.
    """
    summary = client.get_analytics_summary()

    if not summary:
        console.print(
            "[yellow]Analytics unavailable — is the memory server running?[/yellow]"
        )
        console.print(f"Server: [dim]{config.api_url}[/dim]")
        return

    # --- Header panel --------------------------------------------------------
    total_memories: int = summary.get("total_memories", 0)
    tokens_saved: int = summary.get("tokens_saved", 0)
    cost_saved: float = summary.get("cost_saved_usd", 0.0)
    compression: float = summary.get("compression_ratio", 0.0)

    header_text = (
        f"[bold white]Total Memories[/bold white]   {total_memories:,}\n"
        f"[bold green]Tokens Saved[/bold green]     {tokens_saved:,}\n"
        f"[bold cyan]Cost Saved[/bold cyan]       ${cost_saved:.4f}\n"
        f"[bold yellow]Compression[/bold yellow]      {compression:.1f}x"
    )
    console.print(
        Panel(
            header_text,
            title="[bold]AI Memory Layer — Economics[/bold]",
            border_style="bright_blue",
            expand=False,
        )
    )

    # --- Provider breakdown table --------------------------------------------
    provider_stats: list[dict] = summary.get("provider_stats", [])
    if provider_stats:
        table = Table(
            title="Provider Breakdown",
            box=box.ROUNDED,
            highlight=True,
        )
        table.add_column("Provider", style="cyan")
        table.add_column("Captures", style="white", justify="right")
        table.add_column("Tokens Saved", style="green", justify="right")
        table.add_column("Cost Saved", style="yellow", justify="right")

        for row in provider_stats:
            table.add_row(
                row.get("platform", "—"),
                f"{row.get('capture_count', 0):,}",
                f"{row.get('tokens_saved', 0):,}",
                f"${row.get('cost_saved_usd', 0.0):.4f}",
            )
        console.print(table)

    # --- Recent activity -----------------------------------------------------
    recent: list[dict] = summary.get("recent_activity", [])
    if recent:
        recent_table = Table(title="Recent Activity", box=box.SIMPLE_HEAD)
        recent_table.add_column("Date", style="dim")
        recent_table.add_column("Platform", style="cyan")
        recent_table.add_column("Summary", style="white", max_width=60)

        for item in recent[:5]:
            recent_table.add_row(
                (item.get("captured_at") or "")[:10],
                item.get("source_platform", "—"),
                (item.get("summary") or "")[:80],
            )
        console.print(recent_table)


# ---------------------------------------------------------------------------
# auth login
# ---------------------------------------------------------------------------


@cli.group()
def auth() -> None:
    """Authentication commands."""


@auth.command("login")
@click.option("--email", default=None, help="Account email.")
@click.option("--password", default=None, help="Account password (not recommended via flag).")
def auth_login(email: Optional[str], password: Optional[str]) -> None:
    """Authenticate with the memory layer and save your token.

    Example:\n
      mem-ai auth login\n
      mem-ai auth login --email user@example.com
    """
    if not email:
        email = Prompt.ask("Email")
    if not password:
        password = getpass.getpass("Password: ")

    console.print(f"Connecting to [cyan]{config.api_url}[/cyan]...")
    result = client.login(email, password)

    if not result:
        console.print("[bold red]Login failed.[/bold red] Check your credentials.")
        sys.exit(1)

    token = result.get("access_token", "")
    config.set("token", token)
    console.print("[bold green]Logged in successfully.[/bold green]")
    console.print(f"Token stored in [dim]{CONFIG_DIR / 'config.json'}[/dim]")


@auth.command("logout")
def auth_logout() -> None:
    """Clear the stored auth token."""
    config.set("token", "")
    console.print("[green]Logged out.[/green]")


@auth.command("status")
def auth_status() -> None:
    """Show current authentication status."""
    if config.is_authenticated:
        console.print("[green]Authenticated.[/green]")
        console.print(f"API: [cyan]{config.api_url}[/cyan]")
    else:
        console.print("[yellow]Not authenticated.[/yellow] Run: mem-ai auth login")


# ---------------------------------------------------------------------------
# setup
# ---------------------------------------------------------------------------


@cli.command()
def setup() -> None:
    """Interactive first-time setup wizard."""
    console.print(
        Panel(
            "[bold]Welcome to mem-ai![/bold]\n\n"
            "This wizard will help you configure the universal AI memory layer.",
            border_style="bright_blue",
        )
    )

    # API URL
    api_url = Prompt.ask(
        "Memory layer API URL",
        default=config.api_url,
    )
    config.set("api_url", api_url)

    # Default provider
    provider = Prompt.ask(
        "Default AI provider",
        choices=list(PROVIDERS.keys()),
        default=config.default_provider,
    )
    config.set("default_provider", provider)

    # Auth
    do_login = Prompt.ask("Log in now?", choices=["y", "n"], default="y")
    if do_login == "y":
        email = Prompt.ask("Email")
        password = getpass.getpass("Password: ")
        result = client.login(email, password)
        if result:
            config.set("token", result.get("access_token", ""))
            console.print("[green]Authentication successful.[/green]")
        else:
            console.print("[yellow]Login skipped (could not connect).[/yellow]")

    console.print(
        f"\n[bold green]Setup complete![/bold green] "
        f"Config saved to [dim]{CONFIG_DIR / 'config.json'}[/dim]\n\n"
        "Try it:\n"
        "  [cyan]mem-ai ask \"What is my current project?\" --provider "
        + provider
        + "[/cyan]"
    )


# ---------------------------------------------------------------------------
# install-hooks
# ---------------------------------------------------------------------------

_ZSHRC_BLOCK = """
# --- mem-ai shell hooks ---------------------------------------------------
# Automatically wrap common AI CLIs with persistent memory context.

function claude() {
  if command -v mem-ai &>/dev/null; then
    mem-ai ask "$*" --provider claude
  else
    command claude "$@"
  fi
}

function ai() {
  if command -v mem-ai &>/dev/null; then
    mem-ai ask "$*" --provider "${MEM_AI_DEFAULT_PROVIDER:-claude}"
  fi
}
# --------------------------------------------------------------------------
"""

_BASHRC_BLOCK = _ZSHRC_BLOCK  # identical syntax for bash


@cli.command("install-hooks")
@click.option(
    "--shell",
    type=click.Choice(["zsh", "bash", "both"]),
    default="both",
    show_default=True,
    help="Which shell config to update.",
)
def install_hooks(shell: str) -> None:
    """Add memory hooks to your shell configuration.

    After running this command, start a new shell session (or source your
    rc file) for the hooks to take effect.

    Example:\n
      mem-ai install-hooks\n
      mem-ai install-hooks --shell zsh
    """
    home = os.path.expanduser("~")
    targets: list[str] = []

    if shell in ("zsh", "both"):
        targets.append(os.path.join(home, ".zshrc"))
    if shell in ("bash", "both"):
        targets.append(os.path.join(home, ".bashrc"))

    for rc_path in targets:
        if not os.path.exists(rc_path):
            console.print(f"[yellow]Skipping {rc_path} — file does not exist.[/yellow]")
            continue

        with open(rc_path) as f:
            existing = f.read()

        if "mem-ai shell hooks" in existing:
            console.print(f"[dim]Hooks already present in {rc_path}[/dim]")
            continue

        with open(rc_path, "a") as f:
            f.write(_ZSHRC_BLOCK)

        console.print(f"[green]Hooks installed in {rc_path}[/green]")

    console.print(
        "\n[bold]Done![/bold] Restart your shell or run:\n"
        "  [cyan]source ~/.zshrc[/cyan]  (or ~/.bashrc)"
    )


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def main() -> None:
    cli()


if __name__ == "__main__":
    main()
