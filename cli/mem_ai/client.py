"""
HTTP client for the AI Memory Layer backend API.

Provides both async and sync versions of every operation.
All methods handle connection errors gracefully — callers receive None / []
instead of exceptions when the memory server is unavailable.
"""

import asyncio
import logging
from typing import Any

import httpx

from mem_ai.config import config

logger = logging.getLogger(__name__)

_TIMEOUT = httpx.Timeout(10.0, connect=5.0)


def _headers() -> dict[str, str]:
    """Return auth headers for the current session token."""
    token = config.token
    if token:
        return {"Authorization": f"Bearer {token}"}
    return {}


# ---------------------------------------------------------------------------
# Async implementation
# ---------------------------------------------------------------------------


async def get_context_async(
    prompt: str,
    platform: str | None = None,
    max_tokens: int | None = None,
) -> dict[str, Any]:
    """Fetch an augmented prompt with injected memory context.

    Calls POST /api/v1/memory/context.

    Returns the full response dict on success, or a minimal fallback dict
    (with ``augmented_prompt`` equal to the raw ``prompt``) on failure so
    callers always get a usable value.
    """
    platform = platform or config.platform
    max_tokens = max_tokens or config.default_max_tokens

    fallback: dict[str, Any] = {
        "original_prompt": prompt,
        "augmented_prompt": prompt,
        "injected_memories": [],
        "context_tokens_used": 0,
    }

    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            resp = await client.post(
                f"{config.api_url}/api/v1/memory/context",
                headers=_headers(),
                json={
                    "prompt": prompt,
                    "platform": platform,
                    "max_tokens": max_tokens,
                    "max_memories": 5,
                },
            )
            resp.raise_for_status()
            return resp.json()
    except httpx.ConnectError:
        logger.warning(
            "Memory server not reachable at %s — skipping context injection.",
            config.api_url,
        )
        return fallback
    except httpx.HTTPStatusError as exc:
        logger.warning("Memory context request failed: %s", exc)
        return fallback
    except Exception as exc:  # noqa: BLE001
        logger.warning("Unexpected error fetching context: %s", exc)
        return fallback


async def capture_async(
    prompt: str,
    response: str,
    platform: str | None = None,
) -> None:
    """Store a prompt/response pair in the memory layer.

    Calls POST /api/v1/memory/capture.
    Failures are logged but never re-raised.
    """
    platform = platform or config.platform

    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            resp = await client.post(
                f"{config.api_url}/api/v1/memory/capture",
                headers=_headers(),
                json={
                    "prompt": prompt,
                    "response": response,
                    "platform": platform,
                },
            )
            resp.raise_for_status()
    except httpx.ConnectError:
        logger.warning(
            "Memory server not reachable at %s — skipping capture.",
            config.api_url,
        )
    except httpx.HTTPStatusError as exc:
        logger.warning("Memory capture request failed: %s", exc)
    except Exception as exc:  # noqa: BLE001
        logger.warning("Unexpected error during capture: %s", exc)


async def search_async(query: str, limit: int = 5) -> list[dict[str, Any]]:
    """Semantic search over stored memories.

    Calls GET /api/v1/memory/search?q=...
    Returns an empty list on failure.
    """
    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            resp = await client.get(
                f"{config.api_url}/api/v1/memory/search",
                headers=_headers(),
                params={"q": query, "limit": limit},
            )
            resp.raise_for_status()
            data = resp.json()
            # API may return {"memories": [...]} or a plain list
            if isinstance(data, list):
                return data
            return data.get("memories", data.get("results", []))
    except httpx.ConnectError:
        logger.warning(
            "Memory server not reachable at %s — returning empty search results.",
            config.api_url,
        )
        return []
    except httpx.HTTPStatusError as exc:
        logger.warning("Memory search failed: %s", exc)
        return []
    except Exception as exc:  # noqa: BLE001
        logger.warning("Unexpected error during search: %s", exc)
        return []


async def forget_async(description: str) -> dict[str, Any]:
    """Mark memories matching *description* as INACTIVE.

    Calls POST /api/v1/memory/forget.
    Returns {"invalidated": N} on success, or {} on failure.
    """
    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            resp = await client.post(
                f"{config.api_url}/api/v1/memory/forget",
                headers=_headers(),
                json={"description": description},
            )
            resp.raise_for_status()
            return resp.json()
    except httpx.ConnectError:
        logger.warning(
            "Memory server not reachable at %s — cannot forget memories.",
            config.api_url,
        )
        return {}
    except httpx.HTTPStatusError as exc:
        logger.warning("Forget request failed: %s", exc)
        return {}
    except Exception as exc:  # noqa: BLE001
        logger.warning("Unexpected error during forget: %s", exc)
        return {}


async def get_analytics_summary_async() -> dict[str, Any]:
    """Fetch analytics / economics summary.

    Calls GET /api/v1/analytics/summary.
    Returns an empty dict on failure.
    """
    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            resp = await client.get(
                f"{config.api_url}/api/v1/analytics/summary",
                headers=_headers(),
            )
            resp.raise_for_status()
            return resp.json()
    except httpx.ConnectError:
        logger.warning(
            "Memory server not reachable at %s — cannot fetch analytics.",
            config.api_url,
        )
        return {}
    except httpx.HTTPStatusError as exc:
        logger.warning("Analytics request failed: %s", exc)
        return {}
    except Exception as exc:  # noqa: BLE001
        logger.warning("Unexpected error fetching analytics: %s", exc)
        return {}


async def login_async(email: str, password: str) -> dict[str, Any] | None:
    """Authenticate and return the token payload, or None on failure."""
    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            resp = await client.post(
                f"{config.api_url}/api/v1/auth/login",
                json={"email": email, "password": password},
            )
            resp.raise_for_status()
            return resp.json()
    except httpx.ConnectError:
        logger.error("Memory server not reachable at %s.", config.api_url)
        return None
    except httpx.HTTPStatusError as exc:
        logger.error("Login failed: %s", exc)
        return None


async def register_async(
    email: str,
    username: str,
    password: str,
) -> dict[str, Any] | None:
    """Register a new user account, returning the created user or None on failure."""
    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            resp = await client.post(
                f"{config.api_url}/api/v1/auth/register",
                json={"email": email, "username": username, "password": password},
            )
            resp.raise_for_status()
            return resp.json()
    except httpx.ConnectError:
        logger.error("Memory server not reachable at %s.", config.api_url)
        return None
    except httpx.HTTPStatusError as exc:
        logger.error("Registration failed: %s", exc)
        return None


# ---------------------------------------------------------------------------
# Synchronous wrappers (thin asyncio.run() shims)
# ---------------------------------------------------------------------------


def get_context(
    prompt: str,
    platform: str | None = None,
    max_tokens: int | None = None,
) -> dict[str, Any]:
    return asyncio.run(get_context_async(prompt, platform, max_tokens))


def capture(
    prompt: str,
    response: str,
    platform: str | None = None,
) -> None:
    asyncio.run(capture_async(prompt, response, platform))


def search(query: str, limit: int = 5) -> list[dict[str, Any]]:
    return asyncio.run(search_async(query, limit))


def forget(description: str) -> dict[str, Any]:
    return asyncio.run(forget_async(description))


def get_analytics_summary() -> dict[str, Any]:
    return asyncio.run(get_analytics_summary_async())


def login(email: str, password: str) -> dict[str, Any] | None:
    return asyncio.run(login_async(email, password))


def register(
    email: str,
    username: str,
    password: str,
) -> dict[str, Any] | None:
    return asyncio.run(register_async(email, username, password))
