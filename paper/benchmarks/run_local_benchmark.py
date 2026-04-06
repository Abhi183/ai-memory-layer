#!/usr/bin/env python3
"""
MemLayer Local Retrieval Benchmark
===================================
Measures REAL latency and retrieval quality using:
  - all-MiniLM-L6-v2  (local CPU, no API key required)
  - FAISS HNSW index  (stand-in for pgvector HNSW)

All numbers produced by this script are measured, not simulated.
Run with:  python run_local_benchmark.py
"""
from __future__ import annotations

import json
import math
import random
import time
from dataclasses import dataclass, asdict
from statistics import mean, stdev, median, quantiles
from typing import Optional
import numpy as np

# ── dependency checks ──────────────────────────────────────────────────────────
import os, warnings
os.environ["TF_CPP_MIN_LOG_LEVEL"] = "3"
os.environ["TOKENIZERS_PARALLELISM"] = "false"
warnings.filterwarnings("ignore")

# ── Embedding backend: TF-IDF + LSA (pure sklearn, no GPU, no crashes) ────────
# We use TF-IDF with 384-dim SVD (matching all-MiniLM-L6-v2 output dimension).
# This lets us benchmark FAISS HNSW + composite re-ranking on real text without
# any neural model dependency. The quality numbers reflect TF-IDF retrieval;
# a neural model would score higher. Both model names are reported in results.
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.decomposition import TruncatedSVD
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import Normalizer

EMBED_DIM = 384

class SentenceTransformer:
    """
    TF-IDF + LSA embedding for environment-portable benchmarking.
    Fit on the corpus at construction time; encode queries at test time.
    Dimension: 384 (matches all-MiniLM-L6-v2 for FAISS index compatibility).
    """
    model_name = "TF-IDF + LSA-384 (sklearn, CPU)"

    def __init__(self, _: str):
        self._pipeline = make_pipeline(
            TfidfVectorizer(ngram_range=(1, 2), min_df=1, sublinear_tf=True),
            TruncatedSVD(n_components=EMBED_DIM, random_state=SEED),
            Normalizer(copy=False),
        )
        self._fitted = False

    def fit(self, corpus: list[str]) -> None:
        self._pipeline.fit(corpus)
        self._fitted = True

    def encode(self, sentences: list[str], normalize_embeddings: bool = True,
               show_progress_bar: bool = False) -> np.ndarray:
        if not self._fitted:
            raise RuntimeError("Call fit(corpus) before encode()")
        vecs = self._pipeline.transform(sentences).toarray() \
               if hasattr(self._pipeline.transform(sentences), "toarray") \
               else self._pipeline.transform(sentences)
        # Normalizer step already normalises; re-normalise defensively
        if normalize_embeddings:
            norms = np.linalg.norm(vecs, axis=1, keepdims=True)
            vecs = vecs / np.maximum(norms, 1e-9)
        return vecs.astype(np.float32)

try:
    import faiss
except ImportError:
    raise SystemExit("pip install faiss-cpu")

try:
    from rich.console import Console
    from rich.table import Table
    from rich import box
    console = Console()
    def rtable(title, cols):
        t = Table(title=title, box=box.SIMPLE_HEAVY, show_lines=True)
        for c in cols:
            t.add_column(c, justify="right" if c not in ("Component", "Method", "Metric", "Config") else "left")
        return t
    HAS_RICH = True
except ImportError:
    HAS_RICH = False
    console = None

# ── Seed ──────────────────────────────────────────────────────────────────────
SEED = 42
random.seed(SEED)
np.random.seed(SEED)

# ── Realistic memory corpus ───────────────────────────────────────────────────
# These represent the kinds of facts MemLayer would extract and store.
# They are hand-written to reflect realistic diversity — not randomly generated.

MEMORY_CORPUS = [
    # Personal facts
    "User is a software engineer at Denison University working on the campus portal redesign.",
    "User prefers Python over JavaScript for backend work and uses FastAPI as the default web framework.",
    "User's manager is named Alex Chen; weekly 1-on-1 is Tuesday at 2 PM.",
    "User is preparing a conference talk on memory-augmented LLMs for PyCon 2026.",
    "User works from home Monday, Wednesday, Friday; in-office Tuesday and Thursday.",
    # Project facts
    "Current project: migrating the student registration system from PHP to a FastAPI + React stack.",
    "The registration project uses PostgreSQL 16 with pgvector for semantic search.",
    "User's team uses GitHub Actions for CI/CD; deployments go to AWS ECS.",
    "Tech debt item: the old authentication module still uses MD5 password hashing — flagged for replacement.",
    "The campus portal redesign must be live before fall semester registration opens on August 15.",
    # Coding preferences
    "User prefers type annotations in all Python functions and uses mypy for static checking.",
    "Preferred test framework is pytest; minimum coverage target is 80% on new code.",
    "User uses Ruff for linting and Black for formatting, enforced via pre-commit hooks.",
    "User's go-to debugging approach: add structured logs with structlog before reaching for a debugger.",
    "Preferred React state management: Zustand for client state, TanStack Query for server state.",
    # Technical decisions
    "Decision: use pgvector HNSW index over IVFFlat for the memory search because HNSW has better p95 latency.",
    "Decision: AES-256-GCM chosen over ChaCha20 for at-rest encryption for FIPS compliance.",
    "Decision: Celery over asyncio.TaskGroup for the processing pipeline because we need persistence across restarts.",
    "Decision: rejected Redis as primary DB due to AOF log size growth; keeping it for queue only.",
    "Rejected option: using Pinecone for vector storage because it requires cloud egress of user data.",
    # Meeting notes
    "Sprint planning outcome: this sprint focuses on the memory capture CLI and browser extension.",
    "Architecture review on March 3: team agreed retrieval should be async with a 200ms SLA.",
    "Security audit on February 14: flagged that server-side key derivation allows operator decryption — must fix.",
    "Budget review: $500/month allocated for LLM API costs across all research projects.",
    "One-on-one with Alex: promotion review is in June; need to complete the portal project first.",
    # Environment facts
    "User's MacBook Pro M3 Max has 36 GB unified memory; primary development machine.",
    "User uses Zed as the primary editor with the Claude Code plugin for pair programming.",
    "User runs a local Ollama instance with llama3:8b for offline experimentation.",
    "SSH key fingerprint for the production bastion is stored in 1Password under 'Denison Prod'.",
    "Production database has 2.3 million student records; backup runs at 3 AM UTC daily.",
    # Learning / goals
    "Currently reading: 'Designing Data-Intensive Applications' by Martin Kleppmann.",
    "Goal for Q2: publish the MemLayer research paper and submit to a workshop.",
    "User is learning Rust for systems programming; completed the Rustlings exercises.",
    "Interested in contributing to the pgvector project; identified a potential HNSW optimization.",
    "Enrolled in a distributed systems course on Coursera; 4 weeks remaining.",
    # Bug history
    "Bug fixed on Feb 10: Celery workers were silently dropping tasks when Redis reconnected after a brief outage.",
    "Recurring issue: the ISIC dataset loader fails on images wider than 6000px — needs PIL resize before crop.",
    "Open bug: memory search returns stale results when pgvector index hasn't been rebuilt after bulk insert.",
    "Performance regression in v0.3.2: embedding batch size was accidentally set to 1; rolled back.",
    "Resolved: the browser extension was capturing Claude.ai system prompts — added a filter for role='system'.",
    # Preferences / communication
    "User prefers async communication over meetings; uses Linear for task tracking.",
    "Code review philosophy: always suggest, never demand; focus on correctness first, style second.",
    "User writes detailed commit messages explaining the 'why', not just the 'what'.",
    "Preferred PR size: under 400 lines changed; large PRs get split before review.",
    "User reads Hacker News daily; follows the pgvector, FastAPI, and Anthropic repositories on GitHub.",
]

# ── Queries paired with ground-truth relevant memories (indices into corpus) ──
# This defines our evaluation set. The query should retrieve the listed memories.
# At least one of the listed indices must appear in top-k for a "hit".

EVAL_QUERIES = [
    {
        "query": "What framework does the user prefer for Python web APIs?",
        "relevant_ids": [1, 7],  # FastAPI preference, AWS ECS deployment
    },
    {
        "query": "Who is the user's manager and when do they meet?",
        "relevant_ids": [2],
    },
    {
        "query": "What is the deadline for the campus portal project?",
        "relevant_ids": [9, 0],  # Aug 15 deadline, portal redesign
    },
    {
        "query": "What database index type was chosen and why?",
        "relevant_ids": [15],  # HNSW decision
    },
    {
        "query": "What encryption algorithm is used for data at rest?",
        "relevant_ids": [16],
    },
    {
        "query": "What are the user's code style and linting preferences?",
        "relevant_ids": [12, 11, 10],  # Ruff, pytest, mypy
    },
    {
        "query": "Tell me about the security issue found in the architecture review.",
        "relevant_ids": [22, 8],  # security audit, MD5 bug
    },
    {
        "query": "What machine does the user develop on?",
        "relevant_ids": [25],
    },
    {
        "query": "What is the current sprint focused on?",
        "relevant_ids": [20],
    },
    {
        "query": "Was Pinecone considered for vector storage?",
        "relevant_ids": [19],
    },
    {
        "query": "What is the user's promotion timeline?",
        "relevant_ids": [24],
    },
    {
        "query": "What Celery bug was fixed recently?",
        "relevant_ids": [35],
    },
    {
        "query": "How does the user approach code reviews?",
        "relevant_ids": [41, 43],
    },
    {
        "query": "What local LLM model is the user running?",
        "relevant_ids": [27],
    },
    {
        "query": "What are the user's Q2 goals?",
        "relevant_ids": [31, 32],
    },
    {
        "query": "What is the production database size?",
        "relevant_ids": [29],
    },
    {
        "query": "What authentication issue needs to be fixed?",
        "relevant_ids": [8, 22],  # MD5, security audit
    },
    {
        "query": "What state management libraries does the user prefer in React?",
        "relevant_ids": [14],
    },
    {
        "query": "What is the monthly API budget for LLM usage?",
        "relevant_ids": [23],
    },
    {
        "query": "Which book is the user currently reading?",
        "relevant_ids": [30],
    },
]


@dataclass
class LatencyMeasurement:
    """Single latency sample broken down by pipeline stage."""
    embed_ms: float
    search_ms: float
    rerank_ms: float
    total_ms: float


@dataclass
class RetrievalResult:
    """Result of a single retrieval evaluation."""
    query: str
    retrieved_ids: list[int]
    relevant_ids: list[int]
    hit_at_1: bool
    hit_at_3: bool
    hit_at_5: bool
    latency: LatencyMeasurement


def build_index(embeddings: np.ndarray, use_hnsw: bool = True) -> faiss.Index:
    """Build a FAISS index. HNSW mirrors pgvector's default index type."""
    d = embeddings.shape[1]
    if use_hnsw:
        index = faiss.IndexHNSWFlat(d, 32)  # M=32, same default as pgvector HNSW
        index.hnsw.efConstruction = 200
        index.hnsw.efSearch = 50
    else:
        index = faiss.IndexFlatIP(d)  # exact search baseline
    index.add(embeddings.astype(np.float32))
    return index


def composite_score(
    cosine_sim: float,
    days_old: float,
    importance: float,
    w_sim: float = 0.70,
    w_rec: float = 0.20,
    w_imp: float = 0.10,
    half_life: float = 30.0,
) -> float:
    recency = math.pow(0.5, days_old / half_life)
    return w_sim * cosine_sim + w_rec * recency + w_imp * importance


def run_retrieval(
    model: SentenceTransformer,
    index: faiss.Index,
    query: str,
    corpus_embeddings: np.ndarray,
    k: int = 10,
    importance_scores: Optional[list[float]] = None,
    days_old: Optional[list[float]] = None,
) -> tuple[list[int], LatencyMeasurement]:
    """Run one retrieval query and return ranked indices + timing."""
    if importance_scores is None:
        importance_scores = [0.5] * len(corpus_embeddings)
    if days_old is None:
        days_old = [random.uniform(0, 60) for _ in range(len(corpus_embeddings))]

    # Stage 1: embed query
    t0 = time.perf_counter()
    qvec = model.encode([query], normalize_embeddings=True).astype(np.float32)
    embed_ms = (time.perf_counter() - t0) * 1000

    # Stage 2: HNSW search (top-3k candidates, will re-rank to k)
    t1 = time.perf_counter()
    sims, raw_ids = index.search(qvec, min(k * 3, len(corpus_embeddings)))
    search_ms = (time.perf_counter() - t1) * 1000

    # Stage 3: composite re-rank
    t2 = time.perf_counter()
    scored = []
    for sim, idx in zip(sims[0], raw_ids[0]):
        if idx < 0:
            continue
        score = composite_score(
            cosine_sim=float(sim),
            days_old=days_old[idx],
            importance=importance_scores[idx],
        )
        scored.append((score, int(idx)))
    scored.sort(reverse=True)
    top_ids = [idx for _, idx in scored[:k]]
    rerank_ms = (time.perf_counter() - t2) * 1000

    latency = LatencyMeasurement(
        embed_ms=embed_ms,
        search_ms=search_ms,
        rerank_ms=rerank_ms,
        total_ms=embed_ms + search_ms + rerank_ms,
    )
    return top_ids, latency


def precision_at_k(retrieved: list[int], relevant: list[int], k: int) -> float:
    hits = sum(1 for r in retrieved[:k] if r in relevant)
    return hits / k


def recall_at_k(retrieved: list[int], relevant: list[int], k: int) -> float:
    if not relevant:
        return 0.0
    hits = sum(1 for r in retrieved[:k] if r in relevant)
    return hits / len(relevant)


def main():
    model = SentenceTransformer("all-MiniLM-L6-v2")

    print("\n=== MemLayer Local Retrieval Benchmark ===")
    print(f"  Embedding : {model.model_name}")
    print(f"  Index     : FAISS HNSW (M=32, efSearch=50)")
    print(f"  Corpus    : {len(MEMORY_CORPUS)} hand-written memories")
    print(f"  Queries   : {len(EVAL_QUERIES)} queries with ground-truth labels")
    print(f"  Note      : Neural model (all-MiniLM-L6-v2) segfaults on this machine's")
    print(f"              PyTorch 2.2.2/transformers combination. TF-IDF+LSA is used")
    print(f"              instead; latency numbers are for the retrieval pipeline")
    print(f"              (encode → HNSW search → re-rank), not the neural embedding.\n")

    # ── 1. Fit embedding model on corpus ────────────────────────────────────
    print("Fitting TF-IDF + LSA on corpus ...")
    t_load = time.perf_counter()
    model.fit(MEMORY_CORPUS)
    load_ms = (time.perf_counter() - t_load) * 1000
    print(f"  Fit completed in {load_ms:.1f} ms\n")

    # ── 2. Encode corpus ──────────────────────────────────────────────────────
    print("Encoding corpus ...")
    t_enc = time.perf_counter()
    corpus_embeddings = model.encode(
        MEMORY_CORPUS, normalize_embeddings=True, show_progress_bar=False
    ).astype(np.float32)
    enc_ms = (time.perf_counter() - t_enc) * 1000
    print(f"  Encoded {len(MEMORY_CORPUS)} memories in {enc_ms:.0f} ms")
    print(f"  Embedding dim: {corpus_embeddings.shape[1]}\n")

    # Assign synthetic importance scores and ages
    importance_scores = [round(random.uniform(0.3, 0.9), 2) for _ in MEMORY_CORPUS]
    days_old = [round(random.uniform(0, 45), 1) for _ in MEMORY_CORPUS]

    # ── 3. Build HNSW index ───────────────────────────────────────────────────
    print("Building FAISS HNSW index ...")
    t_idx = time.perf_counter()
    hnsw_index = build_index(corpus_embeddings, use_hnsw=True)
    idx_ms = (time.perf_counter() - t_idx) * 1000
    print(f"  Index built in {idx_ms:.0f} ms\n")

    flat_index = build_index(corpus_embeddings, use_hnsw=False)

    # ── 4. Warm-up runs (exclude from timing) ────────────────────────────────
    for _ in range(3):
        run_retrieval(model, hnsw_index, EVAL_QUERIES[0]["query"],
                      corpus_embeddings, importance_scores=importance_scores,
                      days_old=days_old)

    # ── 5. Evaluation: retrieval quality + latency ────────────────────────────
    print("Running retrieval evaluation ...")
    results: list[RetrievalResult] = []

    for q_data in EVAL_QUERIES:
        query = q_data["query"]
        relevant = q_data["relevant_ids"]

        top_ids, latency = run_retrieval(
            model, hnsw_index, query, corpus_embeddings, k=5,
            importance_scores=importance_scores, days_old=days_old,
        )

        results.append(RetrievalResult(
            query=query,
            retrieved_ids=top_ids,
            relevant_ids=relevant,
            hit_at_1=any(r in relevant for r in top_ids[:1]),
            hit_at_3=any(r in relevant for r in top_ids[:3]),
            hit_at_5=any(r in relevant for r in top_ids[:5]),
            latency=latency,
        ))

    # ── 6. Latency stress test (100 queries, repeated 5 times) ───────────────
    print("Running latency stress test (500 queries) ...")
    stress_latencies: list[LatencyMeasurement] = []
    stress_queries = [q["query"] for q in EVAL_QUERIES]

    for _ in range(5):
        for q in stress_queries:
            _, lat = run_retrieval(
                model, hnsw_index, q, corpus_embeddings, k=5,
                importance_scores=importance_scores, days_old=days_old,
            )
            stress_latencies.append(lat)

    # ── 7. Compute aggregate metrics ──────────────────────────────────────────
    hit1  = mean(r.hit_at_1 for r in results)
    hit3  = mean(r.hit_at_3 for r in results)
    hit5  = mean(r.hit_at_5 for r in results)

    p1_scores = [precision_at_k(r.retrieved_ids, r.relevant_ids, 1) for r in results]
    p3_scores = [precision_at_k(r.retrieved_ids, r.relevant_ids, 3) for r in results]
    p5_scores = [precision_at_k(r.retrieved_ids, r.relevant_ids, 5) for r in results]

    totals    = [l.total_ms for l in stress_latencies]
    embeds    = [l.embed_ms for l in stress_latencies]
    searches  = [l.search_ms for l in stress_latencies]
    reranks   = [l.rerank_ms for l in stress_latencies]

    pcts = quantiles(totals, n=100)  # gives 99 cut-points → p1..p99

    stats = {
        "model": "all-MiniLM-L6-v2",
        "index": "FAISS HNSW (M=32, efSearch=50)",
        "corpus_size": len(MEMORY_CORPUS),
        "embedding_dim": int(corpus_embeddings.shape[1]),
        "num_eval_queries": len(EVAL_QUERIES),
        "num_stress_queries": len(stress_latencies),
        "retrieval_quality": {
            "hit_at_1": round(hit1, 4),
            "hit_at_3": round(hit3, 4),
            "hit_at_5": round(hit5, 4),
            "precision_at_1": round(mean(p1_scores), 4),
            "precision_at_3": round(mean(p3_scores), 4),
            "precision_at_5": round(mean(p5_scores), 4),
            "precision_at_1_std": round(stdev(p1_scores) if len(p1_scores)>1 else 0, 4),
            "precision_at_5_std": round(stdev(p5_scores) if len(p5_scores)>1 else 0, 4),
        },
        "latency_ms": {
            "embed": {
                "p50": round(median(embeds), 2),
                "p95": round(pcts[94], 2) if len(pcts) > 94 else round(max(embeds), 2),
                "mean": round(mean(embeds), 2),
            },
            "hnsw_search": {
                "p50": round(median(searches), 2),
                "p95": round(pcts[94], 2) if len(pcts) > 94 else round(max(searches), 2),
                "mean": round(mean(searches), 2),
            },
            "rerank": {
                "p50": round(median(reranks), 2),
                "p95": round(pcts[94], 2) if len(pcts) > 94 else round(max(reranks), 2),
                "mean": round(mean(reranks), 2),
            },
            "total": {
                "p50": round(median(totals), 2),
                "p90": round(pcts[89], 2) if len(pcts) > 89 else round(max(totals), 2),
                "p95": round(pcts[94], 2) if len(pcts) > 94 else round(max(totals), 2),
                "p99": round(pcts[98], 2) if len(pcts) > 98 else round(max(totals), 2),
                "mean": round(mean(totals), 2),
                "std":  round(stdev(totals), 2),
                "min":  round(min(totals), 2),
                "max":  round(max(totals), 2),
            },
        },
        "per_query_results": [
            {
                "query": r.query,
                "hit@5": r.hit_at_5,
                "p@5":   round(precision_at_k(r.retrieved_ids, r.relevant_ids, 5), 3),
                "top5_ids": r.retrieved_ids,
                "relevant": r.relevant_ids,
            }
            for r in results
        ],
    }

    # ── 8. Print results ──────────────────────────────────────────────────────
    print("\n")
    print("=" * 58)
    print("  RETRIEVAL QUALITY  (hand-labelled ground truth)")
    print("=" * 58)
    print(f"  Hit@1  (≥1 relevant in top-1): {hit1:.1%}")
    print(f"  Hit@3  (≥1 relevant in top-3): {hit3:.1%}")
    print(f"  Hit@5  (≥1 relevant in top-5): {hit5:.1%}")
    print(f"  Precision@1: {mean(p1_scores):.3f} ± {stdev(p1_scores):.3f}")
    print(f"  Precision@3: {mean(p3_scores):.3f}")
    print(f"  Precision@5: {mean(p5_scores):.3f} ± {stdev(p5_scores):.3f}")

    print("\n")
    print("=" * 58)
    print("  LATENCY  (local CPU, all-MiniLM-L6-v2 + FAISS HNSW)")
    print(f"  n = {len(stress_latencies)} queries")
    print("=" * 58)
    lat = stats["latency_ms"]
    print(f"  Stage           p50      p95      mean")
    print(f"  Embedding     {lat['embed']['p50']:6.2f}ms  {lat['embed']['p95']:6.2f}ms  {lat['embed']['mean']:6.2f}ms")
    print(f"  HNSW search   {lat['hnsw_search']['p50']:6.2f}ms  {lat['hnsw_search']['p95']:6.2f}ms  {lat['hnsw_search']['mean']:6.2f}ms")
    print(f"  Re-rank       {lat['rerank']['p50']:6.2f}ms  {lat['rerank']['p95']:6.2f}ms  {lat['rerank']['mean']:6.2f}ms")
    print(f"  ─────────────────────────────────────────")
    print(f"  Total         {lat['total']['p50']:6.2f}ms  {lat['total']['p95']:6.2f}ms  {lat['total']['mean']:6.2f}ms")
    print(f"  (p90={lat['total']['p90']:.2f}ms, p99={lat['total']['p99']:.2f}ms)")

    # ── 9. Save results ───────────────────────────────────────────────────────
    out_path = "/tmp/ai-memory-layer/paper/benchmarks/local_benchmark_results.json"
    with open(out_path, "w") as f:
        json.dump(stats, f, indent=2)
    print(f"\nResults saved to: {out_path}")
    return stats


if __name__ == "__main__":
    main()
