# AI Memory Layer — System Architecture

## Overview

AI Memory Layer is a universal persistent memory system for AI agents. It sits between the user and any LLM-powered tool, capturing every interaction, extracting durable knowledge, and injecting relevant context before each new prompt.

```
┌─────────────────────────────────────────────────────────────────────┐
│                         USER WORKFLOW                               │
│                                                                     │
│  ChatGPT / Claude / Cursor / Notion AI                             │
│       │                          ▲                                  │
│       │ (prompt)                 │ (augmented prompt)               │
│       ▼                          │                                  │
│  ┌──────────────────────────────────────────────────────────────┐  │
│  │               BROWSER EXTENSION / CLI WRAPPER               │  │
│  │  • Intercepts outgoing prompts                              │  │
│  │  • Calls /memory/context to inject relevant memories        │  │
│  │  • After response: calls /memory/capture to store exchange  │  │
│  └──────────────────────────┬───────────────────────────────────┘  │
│                             │ HTTP                                   │
└─────────────────────────────┼───────────────────────────────────────┘
                              │
┌─────────────────────────────▼───────────────────────────────────────┐
│                      FASTAPI BACKEND                                │
│                                                                     │
│  ┌──────────────┐  ┌──────────────────┐  ┌──────────────────────┐  │
│  │  Auth Layer  │  │  Memory API      │  │  Context API         │  │
│  │  JWT tokens  │  │  CRUD + capture  │  │  Prompt augmentation │  │
│  └──────────────┘  └────────┬─────────┘  └──────────┬───────────┘  │
│                             │                        │              │
│  ┌──────────────────────────▼────────────────────────▼───────────┐  │
│  │                   REDIS QUEUE (Celery)                        │  │
│  └────────────────────────────┬──────────────────────────────────┘  │
│                               │                                     │
│  ┌────────────────────────────▼──────────────────────────────────┐  │
│  │                 MEMORY PROCESSING PIPELINE                    │  │
│  │                                                               │  │
│  │  1. Decrypt raw content                                       │  │
│  │  2. Extract facts  ──► GPT-4o-mini                           │  │
│  │  3. Summarize      ──► GPT-4o-mini                           │  │
│  │  4. Classify type  ──► short_term | long_term                │  │
│  │  5. Chunk text     ──► max 512 tokens, 50-token overlap      │  │
│  │  6. Embed chunks   ──► OpenAI / sentence-transformers        │  │
│  │  7. Store vectors  ──► pgvector (cosine similarity index)    │  │
│  └────────────────────────────┬──────────────────────────────────┘  │
│                               │                                     │
└───────────────────────────────┼─────────────────────────────────────┘
                                │
┌───────────────────────────────▼─────────────────────────────────────┐
│                      STORAGE LAYER                                  │
│                                                                     │
│  ┌─────────────────────────────┐  ┌──────────────────────────────┐  │
│  │   PostgreSQL + pgvector     │  │         Redis                │  │
│  │                             │  │                              │  │
│  │  users                      │  │  • Celery task queue         │  │
│  │  memories (AES-256-GCM)     │  │  • API response cache        │  │
│  │  memory_embeddings (vector) │  │  • Session store             │  │
│  │  sources                    │  │                              │  │
│  │  tags / memory_tags         │  └──────────────────────────────┘  │
│  └─────────────────────────────┘                                    │
└─────────────────────────────────────────────────────────────────────┘
```

---

## Component Deep-Dives

### 1. Memory Capture Layer

| Method | How it works |
|--------|-------------|
| Browser extension | Content scripts detect DOM changes on ChatGPT/Claude, extract prompt+response, POST to `/memory/capture` |
| CLI wrapper | `mem-cli record "prompt" "response" --platform cursor` |
| API (direct) | Developers POST to `/memory/capture` with custom platform name |
| SDK | Python/JS SDK wraps the API client |

### 2. Memory Processing Pipeline

```
RAW CAPTURE
    │
    ▼
[CELERY TASK] process_memory
    │
    ├─► decrypt(content, user_salt)
    │
    ├─► LLM: extract_facts()
    │       → { "facts": ["Works at Acme Corp", "Uses Python daily"] }
    │
    ├─► LLM: summarize()
    │       → "User asked for help debugging a React hook. Resolved by..."
    │
    ├─► LLM: classify_type()
    │       → "long_term" (has durable personal facts) | "short_term"
    │
    ├─► chunk_text()   (512-token chunks, 50-token overlap)
    │
    ├─► embed(chunks)  (OpenAI text-embedding-3-small → 1536-dim)
    │
    └─► store(embedding, metadata) → status = ACTIVE
```

### 3. Memory Storage Schema

```sql
users
  id UUID PK
  email TEXT UNIQUE
  username TEXT UNIQUE
  hashed_password TEXT       -- bcrypt
  encryption_salt TEXT       -- per-user AES-256-GCM key derivation salt
  created_at TIMESTAMPTZ

memories
  id UUID PK
  user_id UUID FK → users
  source_id UUID FK → sources
  content TEXT               -- AES-256-GCM encrypted
  summary TEXT               -- AES-256-GCM encrypted
  extracted_facts JSONB      -- { "facts": [...] }
  memory_type ENUM(short_term, long_term, semantic)
  status ENUM(pending, processing, active, archived, failed)
  source_platform TEXT
  token_count INT
  importance_score FLOAT     -- 0.0–1.0
  access_count INT
  captured_at TIMESTAMPTZ
  processed_at TIMESTAMPTZ
  expires_at TIMESTAMPTZ     -- NULL = no expiry

memory_embeddings
  id UUID PK
  memory_id UUID FK → memories (UNIQUE)
  user_id UUID FK → users
  embedding VECTOR(1536)     -- pgvector; HNSW/IVFFlat indexed
  model_name TEXT
  created_at TIMESTAMPTZ

sources
  id UUID PK
  user_id UUID FK → users
  platform TEXT              -- chatgpt | claude | cursor | notion
  source_url TEXT
  session_id TEXT
  metadata JSONB

tags
  id UUID PK
  name TEXT UNIQUE
  color TEXT

memory_tags (junction)
  memory_id UUID FK → memories
  tag_id UUID FK → tags
```

### 4. Retrieval Algorithm

```
Query: "Write email to my manager"

Step 1 — Embed query
  query_vec = embed("Write email to my manager")   # 1536-dim

Step 2 — Vector search (pgvector)
  SELECT memory, 1 - (embedding <=> query_vec) AS cosine_sim
  FROM memory_embeddings
  JOIN memories ON memories.id = memory_id
  WHERE user_id = $user AND status = 'active'
  ORDER BY embedding <=> query_vec
  LIMIT 15

Step 3 — Re-rank with composite score
  final_score = 0.70 × cosine_sim
              + 0.20 × recency_score(captured_at)   # exp decay, 30-day half-life
              + 0.10 × importance_score

Step 4 — Filter below threshold (default 0.65)

Step 5 — Build context block
  [MEMORY CONTEXT]
  - User works as Software Engineer at Denison University
  - User's manager is named Alex Chen
  - User is working on the campus portal redesign project
  [END CONTEXT]

  Write email to my manager

Step 6 — Return augmented_prompt to caller
```

### 5. Encryption Design

```
Server secret key (env var)  +  User salt (stored in DB)
         │                              │
         └──── PBKDF2-HMAC-SHA256 ──────┘
                    │
              256-bit AES key
                    │
              AES-256-GCM
              (nonce: 12 random bytes, prepended to ciphertext)
                    │
           base64(nonce || ciphertext+tag)
                    │
              stored in DB
```

Key properties:
- **No key storage** — keys are re-derived on every operation, never persisted.
- **Per-user isolation** — each user's salt means their key is unique.
- **Tamper detection** — GCM authentication tag detects any modification.
- **Key rotation** — change server secret → re-encrypt all memories (migration script needed).

---

## API Reference

### Authentication

```
POST /api/v1/auth/register
{
  "email": "user@example.com",
  "username": "johndoe",
  "password": "securepass123"
}
→ 201 { "id": "...", "email": "...", "username": "...", "created_at": "..." }

POST /api/v1/auth/login
{ "email": "...", "password": "..." }
→ 200 { "access_token": "eyJ...", "token_type": "bearer", "expires_in": 86400 }
```

### Memory endpoints

```
POST   /api/v1/memory/capture          Capture raw prompt+response (async processing)
POST   /api/v1/memory/                 Create memory manually
GET    /api/v1/memory/                 List memories (filter by type, platform)
GET    /api/v1/memory/search?q=...     Semantic similarity search
POST   /api/v1/memory/context          Get augmented prompt with injected context
GET    /api/v1/memory/{id}             Get single memory
PATCH  /api/v1/memory/{id}             Update memory
DELETE /api/v1/memory/{id}             Delete memory
```

### Context injection example

```
POST /api/v1/memory/context
{
  "prompt": "Write email to my manager",
  "platform": "chatgpt",
  "max_tokens": 800,
  "max_memories": 5
}

Response:
{
  "original_prompt": "Write email to my manager",
  "augmented_prompt": "[MEMORY CONTEXT]\n- User is a software engineer at Denison...\n[END CONTEXT]\n\nWrite email to my manager",
  "injected_memories": [...],
  "context_tokens_used": 120
}
```

---

## 30-Day MVP Roadmap

### Week 1 — Core Memory Engine
- [x] PostgreSQL + pgvector schema
- [x] AES-256-GCM encryption service
- [x] Embedding service (OpenAI + local fallback)
- [x] Memory processing pipeline (Celery)
- [x] FastAPI CRUD + auth

### Week 2 — Retrieval System
- [ ] Tune IVFFlat index (set `lists` = sqrt(expected_row_count))
- [ ] A/B test scoring weights (W_SIMILARITY, W_RECENCY, W_IMPORTANCE)
- [ ] Add full-text search fallback (for when embeddings not yet generated)
- [ ] Redis caching for frequent queries

### Week 3 — Browser Extension
- [x] Manifest v3 skeleton
- [x] ChatGPT + Claude content scripts
- [ ] Notion AI content script
- [ ] Context injection UI overlay (show injected memories visually)
- [ ] Extension settings page

### Week 4 — Integration & Polish
- [x] React dashboard (list, search, context preview)
- [ ] Memory export (JSON / Markdown)
- [ ] Importance score tuning UI
- [ ] Rate limiting (slowapi)
- [ ] End-to-end tests

---

## Scaling to Millions of Users

```
Current (MVP):          Scaled:
─────────────────       ──────────────────────────────────────
PostgreSQL (single)  →  PostgreSQL read replicas + connection pooling (PgBouncer)
pgvector             →  pgvector with HNSW index OR Qdrant/Weaviate cluster
Redis (single)       →  Redis Cluster / ElastiCache
Celery workers       →  Kubernetes HPA (horizontal pod autoscaler)
FastAPI (single)     →  Multiple pods behind load balancer (ALB/nginx)

For > 10M memories per user:
  • Shard memory_embeddings by user_id hash
  • Use dedicated vector DB (Qdrant) with user namespaces
  • Async embedding generation with Kafka instead of Celery
  • CDN cache for context responses (TTL: 60s, keyed by user+prompt hash)
```

### Kafka-based pipeline (at scale)

```
Browser Extension
    │
    POST /capture
    │
    ▼
FastAPI Producer ──► Kafka topic: raw-captures
                         │
                    ┌────▼─────────┐
                    │ Consumer 1   │ fact extraction
                    │ Consumer 2   │ summarization    (scale independently)
                    │ Consumer 3   │ embedding
                    └────┬─────────┘
                         │
                    Qdrant / pgvector
```

---

## Future Features

| Feature | Description |
|---------|-------------|
| **Cross-AI sync** | One memory store synchronized across ChatGPT, Claude, Gemini, local LLMs |
| **Agent memory sharing** | Team workspaces — agents share a memory pool (e.g. all engineers at a company) |
| **Knowledge graph** | Extract entity relationships (Person → WorksAt → Company) using Neo4j |
| **Personal AI profile** | Auto-generated profile: skills, preferences, communication style, goals |
| **Memory versioning** | Track how facts change over time (e.g. job change, project completion) |
| **Forgetting curve** | Spaced repetition model: surface memories before they "fade" |
| **On-device mode** | Fully local: Ollama embeddings + SQLite + encrypted local storage |
| **MCP server** | Expose memory as a Model Context Protocol server for any MCP-compatible client |
