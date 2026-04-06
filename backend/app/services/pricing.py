"""
Provider pricing configuration and cost calculation utilities.

All prices are in USD per 1 million input tokens.
Sources: official provider pricing pages as of early 2025.
"""

# Price per 1M input tokens (USD)
PROVIDER_PRICING: dict[str, dict[str, float]] = {
    "claude": {
        "claude-sonnet-4-5": 3.00,
        "claude-opus-4-5": 15.00,
        "claude-haiku-4-5": 0.80,
        # Common aliases / older names
        "claude-3-5-sonnet": 3.00,
        "claude-3-5-haiku": 0.80,
        "claude-3-opus": 15.00,
        "default": 3.00,
    },
    "openai": {
        "gpt-4o": 2.50,
        "gpt-4o-mini": 0.15,
        "gpt-4-turbo": 10.00,
        "gpt-4": 30.00,
        "gpt-3.5-turbo": 0.50,
        "default": 2.50,
    },
    "gemini": {
        "gemini-2.0-flash": 0.10,
        "gemini-1.5-pro": 1.25,
        "gemini-1.5-flash": 0.075,
        "gemini-pro": 0.50,
        "default": 0.50,
    },
    "ollama": {
        # Local inference — effectively free
        "default": 0.0,
    },
    "chatgpt": {
        # chatgpt.com / ChatGPT app (treat as OpenAI pricing)
        "gpt-4o": 2.50,
        "gpt-4o-mini": 0.15,
        "default": 2.50,
    },
    "cursor": {
        # Cursor uses a mix of models; approximate with GPT-4o pricing
        "gpt-4o": 2.50,
        "claude-sonnet-4-5": 3.00,
        "default": 2.50,
    },
    # Global fallback when platform is unknown
    "default": 2.50,
}

_TOKENS_PER_MILLION = 1_000_000


def get_price_per_token(platform: str, model: str) -> float:
    """
    Return the USD price per *single* input token for the given platform/model.

    Lookup order:
        1. platform → exact model name
        2. platform → "default"
        3. global "default"
    """
    platform_key = platform.lower()
    model_key = model.lower()

    platform_table = PROVIDER_PRICING.get(platform_key, {})

    price_per_million: float
    if model_key in platform_table:
        price_per_million = platform_table[model_key]
    elif "default" in platform_table:
        price_per_million = platform_table["default"]
    else:
        # Fall back to the global default
        price_per_million = PROVIDER_PRICING.get("default", 2.50)  # type: ignore[assignment]

    return price_per_million / _TOKENS_PER_MILLION


def calculate_cost_savings(tokens_saved: int, platform: str, model: str) -> float:
    """
    Calculate the USD cost saved by not sending `tokens_saved` tokens to the provider.

    Args:
        tokens_saved: Number of tokens that were *not* sent due to memory compression.
        platform:     Provider identifier (e.g. "claude", "openai", "gemini", "ollama").
        model:        Specific model name (e.g. "claude-sonnet-4-5", "gpt-4o").

    Returns:
        Cost saved in USD, rounded to 6 decimal places.
    """
    if tokens_saved <= 0:
        return 0.0

    price_per_token = get_price_per_token(platform, model)
    savings = tokens_saved * price_per_token
    return round(savings, 6)
