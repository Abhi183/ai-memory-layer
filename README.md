# MemLayer — Universal Encrypted Memory for AI Agents

> **Give Claude, GPT-4, Gemini, and Ollama a persistent memory.**

MemLayer is a universal, encrypted memory layer that sits between you and any AI. It captures every interaction, extracts durable knowledge, and injects only the relevant context into future prompts — so each session picks up where the last one left off without re-sending your entire conversation history.

```
You  →  mem-ai ask "How do I fix this React hook?"
                ↓
        Retrieves relevant memories (~500 tokens of facts)
        instead of re-sending your full session history
                ↓
   claude / gpt-4o / gemini / ollama  →  Answer
                ↓
        Captures this interaction as a new memory
```

**How much it actually saves depends on your session length.** If your conversation history is 10,000 tokens and the injected memory context is 600 tokens, you save 9,400 tokens on that query. The economics dashboard shows you the real numbers from your own usage.

---

## Why MemLayer?

| Problem | MemLayer's answer |
|---------|-------------------|
| LLMs are stateless — every session starts from zero | Persistent encrypted memory store per user |
| Re-sending full history costs more each turn | Extract-compress-retrieve: inject only what matters |
| Memory solutions are provider-locked | Universal adapter: Claude, GPT-4, Gemini, Ollama |
| No visibility into what memory is saving you | Economics engine: tracks real token/cost savings per query |
| Memory stored in the cloud is a privacy risk | AES-256-GCM encryption, per-user key derivation |

---

## Key Features

- **Universal CLI wrapper** — wrap any AI CLI: `mem-ai ask "prompt" --provider claude`
- **Economics dashboard** — see actual tokens saved, cost saved ($), per provider, from your own usage
- **MCP server** — native Claude Code integration via Model Context Protocol
- **Browser extension** — auto-injects memory into ChatGPT and Claude web interfaces
- **Encrypted at rest** — AES-256-GCM with PBKDF2 key derivation, no key storage
- **Composite retrieval** — semantic similarity + recency + importance scoring
- **Self-hostable** — full Docker Compose stack, no cloud dependency

---

## Quick Start

### 1. Start the backend

```bash
cp backend/.env.example backend/.env
# Fill in at least one: OPENAI_API_KEY or ANTHROPIC_API_KEY
docker compose up -d
```

The API is now running at `http://localhost:8000`.  
Dashboard at `http://localhost:3000`.

### 2. Install the CLI

```bash
cd cli
pip install -e .
mem-ai setup          # interactive first-time setup
mem-ai auth login
```

### 3. Use it

```bash
# Wrap any AI in your terminal:
mem-ai ask "How do I write a Rust async function?" --provider claude
mem-ai ask "Review this Python class" --provider openai --model gpt-4o
mem-ai ask "Explain my project structure" --provider gemini
mem-ai ask "Help me debug this" --provider ollama --model llama3

# Search your memories:
mem-ai search "React hooks"

# See your actual savings from your own usage:
mem-ai stats
```

### 4. Claude Code integration (MCP)

Add to `.claude/settings.json`:
```json
{
  "mcpServers": {
    "memory": {
      "command": "python",
      "args": ["-m", "mem_ai.mcp_server"],
      "env": {
        "MEM_AI_API_URL": "http://localhost:8000",
        "MEM_AI_TOKEN": "your-jwt-token"
      }
    }
  }
}
```

Now Claude Code can automatically search your memories and capture new ones.

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│                         USER WORKFLOW                               │
│                                                                     │
│   mem-ai CLI  /  Browser Extension  /  MCP (Claude Code)           │
│        │                                        ▲                  │
│        │ prompt                                  │ augmented prompt │
│        ▼                                        │                  │
│  ┌──────────────────────────────────────────────────────────────┐  │
│  │               MEMORY LAYER  (localhost:8000)                │  │
│  │  • Semantic search over user memories (pgvector)            │  │
│  │  • Composite re-ranking: 0.7×sim + 0.2×recency + 0.1×imp   │  │
│  │  • Token/cost accounting per query                          │  │
│  └──────────────────────────┬───────────────────────────────────┘  │
│                             │                                       │
└─────────────────────────────┼───────────────────────────────────────┘
                              │
              ┌───────────────┼────────────────┐
              ▼               ▼                ▼
          FastAPI         PostgreSQL         Redis
          backend         + pgvector      (Celery queue)
              │
    ┌─────────▼──────────┐
    │  Processing Pipeline│
    │  1. Fact extraction │  ← gpt-4o-mini / claude-haiku
    │  2. Summarize       │
    │  3. Classify type   │
    │  4. Embed (1536-d)  │
    │  5. Store encrypted │  ← AES-256-GCM
    └────────────────────┘
```

### Retrieval Algorithm

```
final_score = 0.70 × cosine_similarity(query, memory)
            + 0.20 × 2^(-days_old / 30)   # recency decay, 30-day half-life
            + 0.10 × importance_score      # 0.0–1.0
```

### How cost savings are calculated

Every call to `/memory/context` logs the token counts and computes the savings:

```
tokens_saved  = full_history_tokens - injected_context_tokens
cost_saved    = tokens_saved × price_per_1M_tokens / 1,000,000
```

The `full_history_tokens` is the actual token count of the conversation history you would have sent without memory. The `injected_context_tokens` is what was actually injected. The difference is what you saved.

Provider pricing used (per 1M input tokens — verify current rates at each provider):

| Provider | Model | Price |
|----------|-------|-------|
| Claude | Sonnet 4.5 | $3.00 |
| Claude | Haiku 4.5 | $0.80 |
| OpenAI | GPT-4o | $2.50 |
| OpenAI | GPT-4o-mini | $0.15 |
| Gemini | 2.0 Flash | $0.10 |
| Ollama | any | $0.00 |

---

## API Reference

### Auth
```
POST /api/v1/auth/register   Register a new user
POST /api/v1/auth/login      Get JWT token
```

### Memory
```
POST /api/v1/memory/capture        Capture prompt+response (async processing)
POST /api/v1/memory/context        Get memory-augmented prompt
GET  /api/v1/memory/search?q=...   Semantic search
GET  /api/v1/memory/               List memories
```

### Analytics (Economics)
```
GET /api/v1/analytics/summary?days=30     Aggregate savings from your usage
GET /api/v1/analytics/timeline?days=30    Daily time series
GET /api/v1/analytics/providers           Per-provider breakdown
GET /api/v1/analytics/logs?limit=50       Raw request log
```

---

## CLI Reference

```
mem-ai ask <prompt>             Send a prompt through the memory layer
  --provider claude|openai|gemini|ollama
  --model <model-name>
  --platform <name>             Tag this session

mem-ai capture <prompt> <resp>  Manually capture an exchange
mem-ai search <query>           Search your memories
mem-ai stats                    Show savings dashboard (from your actual usage)
mem-ai auth login/logout        Authenticate
mem-ai setup                    Interactive first-time setup
mem-ai install-hooks            Add shell hooks to .zshrc/.bashrc
```

---

## Project Structure

```
ai-memory-layer/
├── backend/               FastAPI + PostgreSQL + Celery
│   ├── app/
│   │   ├── api/v1/        REST endpoints (memory, analytics, auth)
│   │   ├── models/        SQLAlchemy models (Memory, AnalyticsLog, ...)
│   │   ├── services/      Business logic (retrieval, pipeline, pricing, analytics)
│   │   └── workers/       Celery async tasks
│   └── alembic/           Database migrations
├── cli/                   Universal terminal CLI wrapper
│   └── mem_ai/
│       ├── providers/     Claude, OpenAI, Gemini, Ollama adapters
│       ├── cli.py         Click CLI entry point
│       └── mcp_server.py  MCP server for Claude Code
├── frontend/              Next.js dashboard
│   ├── app/analytics/     Economics dashboard page
│   └── components/
│       ├── memory/        Memory browser UI
│       └── analytics/     Token savings charts
├── extension/             Chrome/Firefox browser extension
└── paper/                 Academic paper
    ├── memlayer.tex        LaTeX source
    └── memlayer.pdf        Compiled PDF
```

---

## Academic Paper

The paper is at [`paper/memlayer.tex`](paper/memlayer.tex) (compiled [`paper/memlayer.pdf`](paper/memlayer.pdf)).

> **MemLayer: A Universal Encrypted Memory Layer for Cross-Provider LLM Context Efficiency**
>
> This paper describes the system design, the retrieval algorithm, the economics model, and a projected cost analysis based on publicly available provider pricing. Empirical evaluation on real conversational data is ongoing.

---

## Contributing

1. Fork the repo
2. Create a feature branch
3. Run tests: `cd backend && pytest`
4. Open a pull request

---

## License

MIT — see [LICENSE](LICENSE).
