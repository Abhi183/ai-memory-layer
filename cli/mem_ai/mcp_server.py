"""
MCP (Model Context Protocol) server for the AI Memory Layer.

Exposes memory operations as tools so that Claude Code (and any other
MCP-compatible client) can search, capture, and retrieve memories
automatically during coding sessions.

Communication is via stdio using the standard JSON-RPC 2.0 / MCP protocol.

Usage
-----
Add to .claude/settings.json:

    {
      "mcpServers": {
        "memory": {
          "command": "python",
          "args": ["-m", "mem_ai.mcp_server"],
          "env": {
            "MEM_AI_API_URL": "http://localhost:8000",
            "MEM_AI_TOKEN": "${MEM_AI_TOKEN}"
          }
        }
      }
    }

If the `mcp` package is available the server uses the official SDK.
Otherwise it falls back to a minimal hand-rolled JSON-RPC 2.0 server over
stdin/stdout.
"""

from __future__ import annotations

import asyncio
import json
import logging
import sys
from typing import Any

from mem_ai import client as mem_client

logger = logging.getLogger(__name__)

SERVER_INFO = {
    "name": "ai-memory-layer",
    "version": "1.0.0",
    "description": "Universal persistent memory for AI coding sessions",
}

# ---------------------------------------------------------------------------
# Tool definitions (shared between SDK and hand-rolled paths)
# ---------------------------------------------------------------------------

TOOLS: list[dict[str, Any]] = [
    {
        "name": "search_memories",
        "description": (
            "Semantic search over stored memories. "
            "Returns a list of relevant memory snippets ranked by similarity."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Natural language search query.",
                },
                "limit": {
                    "type": "integer",
                    "description": "Maximum number of results to return.",
                    "default": 5,
                },
            },
            "required": ["query"],
        },
    },
    {
        "name": "capture_memory",
        "description": (
            "Store a prompt/response interaction in persistent memory for "
            "future retrieval and context injection."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "prompt": {
                    "type": "string",
                    "description": "The user prompt or question.",
                },
                "response": {
                    "type": "string",
                    "description": "The AI response.",
                },
                "platform": {
                    "type": "string",
                    "description": "Platform / tool label (e.g. 'claude-code').",
                    "default": "claude-code",
                },
            },
            "required": ["prompt", "response"],
        },
    },
    {
        "name": "get_context",
        "description": (
            "Retrieve an augmented prompt with relevant memories injected as "
            "context. Use this before sending a prompt to an LLM to ground "
            "the response in the user's history."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "prompt": {
                    "type": "string",
                    "description": "The raw user prompt to augment.",
                },
                "max_tokens": {
                    "type": "integer",
                    "description": "Maximum tokens to use for injected context.",
                    "default": 800,
                },
            },
            "required": ["prompt"],
        },
    },
    {
        "name": "get_analytics",
        "description": (
            "Return a summary of token savings, cost savings, and usage "
            "statistics across all AI providers."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {},
            "required": [],
        },
    },
]

# ---------------------------------------------------------------------------
# Tool execution
# ---------------------------------------------------------------------------


async def _dispatch_tool(name: str, arguments: dict[str, Any]) -> Any:
    """Route a tool call to the appropriate memory client function."""
    if name == "search_memories":
        query: str = arguments["query"]
        limit: int = arguments.get("limit", 5)
        results = await mem_client.search_async(query, limit=limit)
        # Return a JSON-serialisable summary list
        return [
            {
                "id": m.get("id", ""),
                "summary": m.get("summary") or (m.get("content") or "")[:200],
                "platform": m.get("source_platform", ""),
                "score": m.get("score"),
                "captured_at": m.get("captured_at", ""),
            }
            for m in results
        ]

    elif name == "capture_memory":
        prompt: str = arguments["prompt"]
        response: str = arguments["response"]
        platform: str = arguments.get("platform", "claude-code")
        await mem_client.capture_async(prompt, response, platform=platform)
        return {"status": "captured"}

    elif name == "get_context":
        prompt = arguments["prompt"]
        max_tokens: int = arguments.get("max_tokens", 800)
        ctx = await mem_client.get_context_async(
            prompt, platform="claude-code", max_tokens=max_tokens
        )
        return {
            "augmented_prompt": ctx.get("augmented_prompt", prompt),
            "memories_injected": len(ctx.get("injected_memories", [])),
            "context_tokens_used": ctx.get("context_tokens_used", 0),
        }

    elif name == "get_analytics":
        return await mem_client.get_analytics_summary_async()

    else:
        raise ValueError(f"Unknown tool: {name!r}")


# ---------------------------------------------------------------------------
# Official MCP SDK path
# ---------------------------------------------------------------------------


def _run_with_sdk() -> None:
    """Start the server using the `mcp` Python SDK."""
    from mcp.server import Server  # type: ignore[import]
    from mcp.server.models import InitializationOptions  # type: ignore[import]
    import mcp.server.stdio  # type: ignore[import]
    import mcp.types as types  # type: ignore[import]

    server = Server(SERVER_INFO["name"])

    @server.list_tools()
    async def list_tools() -> list[types.Tool]:
        return [
            types.Tool(
                name=t["name"],
                description=t["description"],
                inputSchema=t["inputSchema"],
            )
            for t in TOOLS
        ]

    @server.call_tool()
    async def call_tool(
        name: str, arguments: dict[str, Any]
    ) -> list[types.TextContent]:
        try:
            result = await _dispatch_tool(name, arguments)
            return [types.TextContent(type="text", text=json.dumps(result, indent=2))]
        except Exception as exc:  # noqa: BLE001
            logger.error("Tool %r raised: %s", name, exc)
            return [
                types.TextContent(
                    type="text", text=json.dumps({"error": str(exc)})
                )
            ]

    async def _main() -> None:
        options = InitializationOptions(
            server_name=SERVER_INFO["name"],
            server_version=SERVER_INFO["version"],
            capabilities=server.get_capabilities(
                notification_options=None,
                experimental_capabilities={},
            ),
        )
        async with mcp.server.stdio.stdio_server() as (read_stream, write_stream):
            await server.run(read_stream, write_stream, options)

    asyncio.run(_main())


# ---------------------------------------------------------------------------
# Hand-rolled JSON-RPC 2.0 fallback
# ---------------------------------------------------------------------------


class _MinimalMCPServer:
    """Minimal MCP server speaking JSON-RPC 2.0 over stdin/stdout."""

    def __init__(self) -> None:
        self._stdin = sys.stdin.buffer
        self._stdout = sys.stdout.buffer

    def _send(self, obj: dict[str, Any]) -> None:
        data = (json.dumps(obj) + "\n").encode()
        self._stdout.write(data)
        self._stdout.flush()

    def _recv(self) -> dict[str, Any] | None:
        line = self._stdin.readline()
        if not line:
            return None
        return json.loads(line.decode().strip())

    async def _handle(self, msg: dict[str, Any]) -> None:
        method: str = msg.get("method", "")
        msg_id = msg.get("id")

        if method == "initialize":
            self._send(
                {
                    "jsonrpc": "2.0",
                    "id": msg_id,
                    "result": {
                        "protocolVersion": "2024-11-05",
                        "capabilities": {"tools": {}},
                        "serverInfo": SERVER_INFO,
                    },
                }
            )

        elif method == "tools/list":
            self._send(
                {
                    "jsonrpc": "2.0",
                    "id": msg_id,
                    "result": {"tools": TOOLS},
                }
            )

        elif method == "tools/call":
            params = msg.get("params", {})
            tool_name: str = params.get("name", "")
            arguments: dict = params.get("arguments", {})
            try:
                result = await _dispatch_tool(tool_name, arguments)
                self._send(
                    {
                        "jsonrpc": "2.0",
                        "id": msg_id,
                        "result": {
                            "content": [
                                {"type": "text", "text": json.dumps(result, indent=2)}
                            ]
                        },
                    }
                )
            except Exception as exc:  # noqa: BLE001
                self._send(
                    {
                        "jsonrpc": "2.0",
                        "id": msg_id,
                        "error": {"code": -32603, "message": str(exc)},
                    }
                )

        elif method == "notifications/initialized":
            # Notification — no response needed
            pass

        elif msg_id is not None:
            # Unknown method that requires a response
            self._send(
                {
                    "jsonrpc": "2.0",
                    "id": msg_id,
                    "error": {"code": -32601, "message": f"Method not found: {method}"},
                }
            )

    def run(self) -> None:
        async def _loop() -> None:
            while True:
                msg = self._recv()
                if msg is None:
                    break
                await self._handle(msg)

        asyncio.run(_loop())


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def main() -> None:
    """Start the MCP server using the best available implementation."""
    logging.basicConfig(
        level=logging.WARNING,
        stream=sys.stderr,
        format="%(levelname)s %(name)s: %(message)s",
    )

    try:
        _run_with_sdk()
    except ImportError:
        logger.info("mcp SDK not available — using hand-rolled JSON-RPC 2.0 server.")
        _MinimalMCPServer().run()


if __name__ == "__main__":
    main()
