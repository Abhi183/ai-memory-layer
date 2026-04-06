"""
Configuration management for mem-ai.

Reads from ~/.mem-ai/config.json or environment variables.
Environment variables take precedence over config file values.
"""

import json
import os
from pathlib import Path
from typing import Any

CONFIG_DIR = Path.home() / ".mem-ai"
CONFIG_FILE = CONFIG_DIR / "config.json"

# Defaults
_DEFAULTS: dict[str, Any] = {
    "api_url": "http://localhost:8000",
    "token": "",
    "platform": "cli",
    "full_context_baseline_tokens": 15000,
    "default_max_tokens": 800,
    "default_provider": "claude",
    "ollama_host": "http://localhost:11434",
    "ollama_model": "llama3",
    "openai_model": "gpt-4o",
    "gemini_model": "gemini-1.5-pro",
}

# ENV variable name mapping: config key -> env var name
_ENV_MAP: dict[str, str] = {
    "api_url": "MEM_AI_API_URL",
    "token": "MEM_AI_TOKEN",
    "platform": "MEM_AI_PLATFORM",
    "full_context_baseline_tokens": "MEM_AI_FULL_CONTEXT_BASELINE_TOKENS",
    "default_max_tokens": "MEM_AI_DEFAULT_MAX_TOKENS",
    "default_provider": "MEM_AI_DEFAULT_PROVIDER",
    "ollama_host": "OLLAMA_HOST",
    "ollama_model": "OLLAMA_MODEL",
    "openai_model": "OPENAI_MODEL",
    "gemini_model": "GEMINI_MODEL",
}


def _load_file() -> dict[str, Any]:
    """Load config from ~/.mem-ai/config.json, returning empty dict on missing/invalid file."""
    if not CONFIG_FILE.exists():
        return {}
    try:
        with CONFIG_FILE.open() as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return {}


def _save_file(data: dict[str, Any]) -> None:
    """Persist config data to ~/.mem-ai/config.json."""
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    with CONFIG_FILE.open("w") as f:
        json.dump(data, f, indent=2)


def _build() -> dict[str, Any]:
    """Merge defaults < file < env vars into one resolved config dict."""
    cfg = dict(_DEFAULTS)
    cfg.update(_load_file())
    for key, env_name in _ENV_MAP.items():
        value = os.environ.get(env_name)
        if value is not None:
            # Cast numeric keys back to int where appropriate
            if key in ("full_context_baseline_tokens", "default_max_tokens"):
                try:
                    value = int(value)  # type: ignore[assignment]
                except ValueError:
                    pass
            cfg[key] = value
    return cfg


class Config:
    """Live view of the resolved configuration.

    Accessing any attribute re-reads the merged config so that env-var
    changes made between calls are always honoured.
    """

    # --- read-only convenience properties ---

    @property
    def api_url(self) -> str:
        return _build()["api_url"].rstrip("/")

    @property
    def token(self) -> str:
        return _build()["token"]

    @property
    def platform(self) -> str:
        return _build()["platform"]

    @property
    def full_context_baseline_tokens(self) -> int:
        return int(_build()["full_context_baseline_tokens"])

    @property
    def default_max_tokens(self) -> int:
        return int(_build()["default_max_tokens"])

    @property
    def default_provider(self) -> str:
        return _build()["default_provider"]

    @property
    def ollama_host(self) -> str:
        return _build()["ollama_host"]

    @property
    def ollama_model(self) -> str:
        return _build()["ollama_model"]

    @property
    def openai_model(self) -> str:
        return _build()["openai_model"]

    @property
    def gemini_model(self) -> str:
        return _build()["gemini_model"]

    @property
    def is_authenticated(self) -> bool:
        return bool(self.token)

    # --- mutation helpers ---

    def set(self, key: str, value: Any) -> None:
        """Persist a single key to the config file."""
        data = _load_file()
        data[key] = value
        _save_file(data)

    def get_all(self) -> dict[str, Any]:
        """Return the fully resolved config dict."""
        return _build()

    def reset(self) -> None:
        """Delete the config file, reverting to defaults."""
        if CONFIG_FILE.exists():
            CONFIG_FILE.unlink()

    # allow dict-style read access as a convenience
    def __getitem__(self, key: str) -> Any:
        return _build()[key]


# Singleton used throughout the package
config = Config()

# Convenience aliases matching the spec naming convention
MEM_AI_API_URL: str = config.api_url
MEM_AI_TOKEN: str = config.token
MEM_AI_PLATFORM: str = config.platform
FULL_CONTEXT_BASELINE_TOKENS: int = config.full_context_baseline_tokens
