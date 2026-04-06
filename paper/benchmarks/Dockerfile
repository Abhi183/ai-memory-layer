# MemLayer Benchmark Container
# Provides a clean, dependency-conflict-free environment for running
# the LOCOMO evaluation harness and latency benchmarks.
#
# Build:  docker build -t memlayer-bench .
# Run:    docker run --rm memlayer-bench
# Output: docker run --rm -v $(pwd)/results:/results memlayer-bench \
#             python locomo_eval.py --output /results/locomo_results.json

FROM python:3.11-slim

LABEL org.opencontainers.image.title="MemLayer Benchmark"
LABEL org.opencontainers.image.description="Reproducible benchmark environment for MemLayer LOCOMO evaluation"

# System-level build dependencies (required for faiss-cpu on some platforms)
RUN apt-get update -qq && \
    apt-get install -y --no-install-recommends \
        build-essential \
        git \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /bench

# Install Python dependencies in a specific order to avoid conflicts:
#   1. PyTorch (CPU-only, small) — sentence-transformers dependency
#   2. faiss-cpu (must be installed before sentence-transformers to avoid BLAS conflicts)
#   3. sentence-transformers + HuggingFace datasets
#   4. tokenization + display utilities
COPY requirements-bench.txt ./
RUN pip install --no-cache-dir -r requirements-bench.txt

# Pre-download the embedding model so the container works offline
RUN python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('all-MiniLM-L6-v2')"

COPY locomo_eval.py run_benchmarks.py run_local_benchmark.py ./

# Default: run the full LOCOMO evaluation and write results
CMD ["python", "locomo_eval.py", "--output", "locomo_results.json"]
