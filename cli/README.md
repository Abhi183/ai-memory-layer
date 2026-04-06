# mem-ai — Universal AI CLI with Persistent Memory

`mem-ai` is a terminal-native wrapper that works with **any** AI CLI or SDK
(Claude, OpenAI, Gemini, Ollama) and automatically injects relevant memory
context from the AI Memory Layer before every prompt.

```
You type:  mem-ai ask "Fix this React bug" --provider claude

What happens:
  1. Retrieves your relevant memories (e.g. "you're using React 18 + Vite")
  2. Augments your prompt with that context
  3. Sends augmented prompt to the AI provider
  4. Streams the response to your terminal
  5. Saves the interaction back to memory for future use
```

---

## Installation

### Prerequisites

- Python 3.11+
- The AI Memory Layer backend running (`docker compose up -d` from the project root)
- At least one AI provider configured (API key in your environment)

### Quick Install

```bash
cd cli/
./install.sh          # installs mem-ai in editable mode
```

Or with a dedicated virtualenv:

```bash
./install.sh --venv
export PATH="$HOME/.mem-ai/venv/bin:$PATH"
```

Or globally:

```bash
./install.sh --global
```

### Manual Install

```bash
pip install -e .
```

---

## First-Time Setup

Run the interactive wizard:

```bash
mem-ai setup
```

This walks you through:
1. Setting the memory layer API URL (default: `http://localhost:8000`)
2. Choosing your default AI provider
3. Authenticating with your account

Or do it step by step:

```bash
# Point to your backend
export MEM_AI_API_URL=http://localhost:8000

# Authenticate
mem-ai auth login

# Verify
mem-ai auth status
```

---

## Usage

### Ask anything

```bash
# Claude (wraps the `claude` CLI)
mem-ai ask "How do I fix this bug in React?" --provider claude

# OpenAI (uses OpenAI Python SDK)
mem-ai ask "Summarize my project status" --provider openai --model gpt-4o

# Gemini (wraps `gemini` CLI or google-generativeai SDK)
mem-ai ask "Write a test for this function" --provider gemini

# Ollama (local models via REST API or subprocess)
mem-ai ask "Explain this algorithm" --provider ollama --model llama3

# Use a custom platform label
mem-ai ask "What is my manager's name?" --provider openai --platform work-assistant
```

### Search your memories

```bash
mem-ai search "React hooks" --limit 5
mem-ai search "authentication patterns"
```

### Manually capture a conversation

```bash
mem-ai capture "What is PBKDF2?" \
  "PBKDF2 is a key derivation function that applies a PRF..." \
  --platform claude
```

### View the economics dashboard

```bash
mem-ai stats
```

Shows:
- Total memories stored
- Tokens saved (avoiding re-sending context you've already discussed)
- Estimated cost savings ($)
- Compression ratio
- Per-provider breakdown

### Authentication

```bash
mem-ai auth login       # log in and save token
mem-ai auth logout      # clear saved token
mem-ai auth status      # check current state
```

### Shell hooks (optional)

Install memory hooks so your regular `claude` command automatically gets
memory context:

```bash
mem-ai install-hooks           # adds hooks to .zshrc AND .bashrc
mem-ai install-hooks --shell zsh
mem-ai install-hooks --shell bash
```

After restarting your shell, typing `claude "my question"` will automatically
route through `mem-ai`.

---

## Provider Setup

### Claude

Install the Claude CLI:

```bash
npm install -g @anthropic-ai/claude-code
```

No API key needed if you're already authenticated with `claude`.

### OpenAI

```bash
export OPENAI_API_KEY=sk-...
```

### Gemini

Option A — Install the Gemini CLI (if available):
```bash
# Follow https://cloud.google.com/gemini/docs/cli
```

Option B — Use the Python SDK directly:
```bash
pip install google-generativeai
export GOOGLE_API_KEY=your-key
```

### Ollama

```bash
# Install Ollama: https://ollama.ai
curl -fsSL https://ollama.ai/install.sh | sh
ollama pull llama3

# mem-ai connects to http://localhost:11434 by default
# Override with:
export OLLAMA_HOST=http://your-ollama-host:11434
```

---

## MCP Server (Claude Code Integration)

`mem-ai` ships an MCP (Model Context Protocol) server that exposes memory
as tools for Claude Code. This enables `claude code` to automatically search
and store memories during coding sessions.

### Configure Claude Code

Add to `.claude/settings.json`:

```json
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
```

Set your token in the environment before starting Claude Code:

```bash
export MEM_AI_TOKEN=$(cat ~/.mem-ai/config.json | python3 -c "import json,sys; print(json.load(sys.stdin)['token'])")
claude
```

### MCP Tools exposed

| Tool | Description |
|------|-------------|
| `search_memories` | Semantic search over stored memories |
| `capture_memory` | Store a prompt/response pair |
| `get_context` | Get an augmented prompt with memory injected |
| `get_analytics` | Return token/cost savings summary |

### Test the MCP server manually

```bash
# Start server
python -m mem_ai.mcp_server

# Send an initialize request (in another terminal or via pipe):
echo '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2024-11-05","capabilities":{},"clientInfo":{"name":"test","version":"0.1"}}}' | python -m mem_ai.mcp_server
```

---

## Configuration Reference

Configuration is read from `~/.mem-ai/config.json` (lowest priority) and
overridden by environment variables (highest priority).

| Config key | Env var | Default | Description |
|------------|---------|---------|-------------|
| `api_url` | `MEM_AI_API_URL` | `http://localhost:8000` | Memory layer backend URL |
| `token` | `MEM_AI_TOKEN` | `""` | JWT auth token |
| `platform` | `MEM_AI_PLATFORM` | `cli` | Default platform label |
| `default_provider` | `MEM_AI_DEFAULT_PROVIDER` | `claude` | Default AI provider |
| `full_context_baseline_tokens` | `MEM_AI_FULL_CONTEXT_BASELINE_TOKENS` | `15000` | Assumed full history baseline |
| `default_max_tokens` | `MEM_AI_DEFAULT_MAX_TOKENS` | `800` | Max tokens for injected context |
| `ollama_host` | `OLLAMA_HOST` | `http://localhost:11434` | Ollama API endpoint |
| `ollama_model` | `OLLAMA_MODEL` | `llama3` | Default Ollama model |
| `openai_model` | `OPENAI_MODEL` | `gpt-4o` | Default OpenAI model |
| `gemini_model` | `GEMINI_MODEL` | `gemini-1.5-pro` | Default Gemini model |

Edit `~/.mem-ai/config.json` directly or use `mem-ai setup` to reconfigure.

---

## Architecture

```
mem-ai ask "Fix React bug" --provider claude
      │
      ├─► GET /api/v1/memory/context   ← memory layer backend
      │     Returns: augmented prompt with relevant memories injected
      │
      ├─► claude -p "{augmented prompt}"   ← AI provider
      │     Streams response to terminal
      │
      └─► POST /api/v1/memory/capture   ← memory layer backend
            Stores interaction for future retrieval
```

---

## Project Structure

```
cli/
├── README.md
├── setup.py
├── requirements.txt
├── install.sh
└── mem_ai/
    ├── __init__.py
    ├── config.py          # Config management (~/.mem-ai/config.json + env vars)
    ├── client.py          # HTTP client for the memory layer API
    ├── cli.py             # Click CLI entry point (mem-ai command)
    ├── mcp_server.py      # MCP server for Claude Code integration
    └── providers/
        ├── __init__.py
        ├── claude_provider.py    # Wraps `claude` CLI subprocess
        ├── openai_provider.py    # Uses openai Python SDK
        ├── gemini_provider.py    # Wraps `gemini` CLI or google-generativeai SDK
        └── ollama_provider.py    # Ollama REST API or subprocess
```
