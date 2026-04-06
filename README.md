# MemLayer — Universal Encrypted Memory for AI Agents

> **Give Claude, GPT-4, Gemini, and Ollama a persistent memory — and see exactly how much it saves you.**

MemLayer is a universal, encrypted memory layer that sits between you and any AI. It captures every interaction, extracts durable knowledge, and injects only the relevant context into future prompts — slashing token usage by ~90% and your API bill along with it.

```
You  →  mem-ai ask "How do I fix this React hook?"
                ↓
        Retrieves 3 relevant memories (142 tokens)
        vs. resending 14,800 tokens of history
                ↓
   claude / gpt-4o / gemini / ollama  →  Answer
                ↓
        Captures this interaction as a new memory
```

---

## Why MemLayer?

| Problem | MemLayer's answer |
|---------|-------------------|
| LLMs are stateless — every session starts from zero | Persistent encrypted memory store per user |
| Context costs scale O(N²) — each turn re-sends all history | Extract-compress-retrieve: inject only what matters |
| Memory solutions are provider-locked | Universal adapter: Claude, GPT-4, Gemini, Ollama |
| No visibility into what memory is saving you | Economics engine: real-time token/cost dashboard |
| Memory stored in the cloud is a privacy risk | AES-256-GCM encryption, per-user key derivation |

---

## Key Features

- **Universal CLI wrapper** — wrap any AI CLI: `mem-ai ask "prompt" --provider claude`
- **Economics dashboard** — see exact tokens saved, cost saved ($), compression ratio per provider
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

# See your savings:
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
│  │  • Token/cost accounting (economics engine)                  │  │
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
            + 0.20 × exp(-days_old / 30)     # recency decay
            + 0.10 × importance_score         # 0.0–1.0
```

### Economics Engine

Every call to `/memory/context` logs:
- `original_tokens`: baseline full-context estimate (15,000 tokens default)
- `augmented_tokens`: actual tokens injected
- `tokens_saved`: the difference
- `cost_saved_usd`: `tokens_saved × price_per_1M_tokens / 1_000_000`

Provider pricing (per 1M input tokens):
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
GET /api/v1/analytics/summary?days=30     Aggregate savings
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
mem-ai stats                    Show economics dashboard
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
└── paper/                 Academic paper + benchmarks
    ├── ai_memory_layer.md Full research paper (5,100 words)
    └── benchmarks/        Reproducible evaluation scripts
```

---

## Benchmarks

From our evaluation on LOCOMO-style synthetic conversations (see `paper/benchmarks/`):

| Method | Avg Tokens/Query | Monthly Cost (team of 10) | Quality |
|--------|-----------------|--------------------------|---------|
| Full context | 15,000 | $847 (Claude Sonnet) | Baseline |
| No memory | 500 | $28 | Degrades over time |
| **MemLayer** | **~1,024** | **$61** | 98% of full-context |

- **93.2% token reduction** vs. full-context baseline
- **Retrieval Precision@5 = 0.84** on synthetic LOCOMO conversations
- **~42ms** median retrieval latency (negligible vs. LLM generation)

Run the benchmarks yourself:
```bash
cd paper/benchmarks
pip install rich tiktoken numpy
python run_benchmarks.py --output results.json
```

---

## Academic Paper

The full research paper is at [`paper/ai_memory_layer.md`](paper/ai_memory_layer.md).

> **MemLayer: A Universal Encrypted Memory Architecture for Cross-Provider LLM Context Efficiency**
>
> Abstract: Large language models are fundamentally stateless — each session starts with no memory of prior interactions. Re-sending conversation history to restore context consumes tokens quadratically, making long-running AI workflows prohibitively expensive. We present MemLayer, a universal encrypted memory layer that intercepts prompts from any AI provider, retrieves semantically relevant memories, and injects only the essential context. MemLayer achieves 93.2% token compression with a composite retrieval score of Precision@5 = 0.84, adding only 42ms median latency. Unlike provider-specific solutions, MemLayer adapts to Claude, GPT-4, Gemini, and Ollama through a unified interface, while an integrated economics engine gives users real-time visibility into cost savings.

---

## Contributing

1. Fork the repo
2. Create a feature branch
3. Run tests: `cd backend && pytest`
4. Open a pull request

---

## License

MIT — see [LICENSE](LICENSE).
