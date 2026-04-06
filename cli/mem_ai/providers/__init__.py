"""Provider implementations for AI CLI wrappers."""

from mem_ai.providers.claude_provider import ClaudeProvider
from mem_ai.providers.openai_provider import OpenAIProvider
from mem_ai.providers.gemini_provider import GeminiProvider
from mem_ai.providers.ollama_provider import OllamaProvider

PROVIDERS = {
    "claude": ClaudeProvider,
    "openai": OpenAIProvider,
    "gemini": GeminiProvider,
    "ollama": OllamaProvider,
}

__all__ = [
    "ClaudeProvider",
    "OpenAIProvider",
    "GeminiProvider",
    "OllamaProvider",
    "PROVIDERS",
]
