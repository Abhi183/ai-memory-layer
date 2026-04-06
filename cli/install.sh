#!/usr/bin/env bash
# ---------------------------------------------------------------------------
# install.sh — Install the mem-ai CLI
#
# Usage:
#   ./install.sh               # install with pip (editable mode)
#   ./install.sh --venv        # create a dedicated virtualenv first
#   ./install.sh --global      # install globally (may need sudo)
# ---------------------------------------------------------------------------

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CONFIG_DIR="$HOME/.mem-ai"
VENV_DIR="$CONFIG_DIR/venv"

GREEN='\033[0;32m'
CYAN='\033[0;36m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
RESET='\033[0m'

info()    { echo -e "${CYAN}[mem-ai]${RESET} $*"; }
success() { echo -e "${GREEN}[mem-ai]${RESET} $*"; }
warn()    { echo -e "${YELLOW}[mem-ai]${RESET} $*"; }
error()   { echo -e "${RED}[mem-ai]${RESET} $*" >&2; exit 1; }

# ---------------------------------------------------------------------------
# Parse flags
# ---------------------------------------------------------------------------
USE_VENV=false
GLOBAL=false

for arg in "$@"; do
  case "$arg" in
    --venv)   USE_VENV=true ;;
    --global) GLOBAL=true ;;
    --help|-h)
      echo "Usage: ./install.sh [--venv] [--global]"
      echo ""
      echo "  --venv    Create a dedicated virtualenv in ~/.mem-ai/venv"
      echo "  --global  Install globally (may require sudo)"
      exit 0
      ;;
    *)
      warn "Unknown argument: $arg"
      ;;
  esac
done

# ---------------------------------------------------------------------------
# Pre-flight checks
# ---------------------------------------------------------------------------
command -v python3 &>/dev/null || error "python3 not found. Install Python 3.11+."
PYTHON_VER=$(python3 -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')
if python3 -c 'import sys; sys.exit(0 if sys.version_info >= (3,11) else 1)' 2>/dev/null; then
  info "Python ${PYTHON_VER} — OK"
else
  error "Python 3.11+ required (found ${PYTHON_VER})."
fi

command -v pip3 &>/dev/null || error "pip3 not found. Install it with: python3 -m ensurepip"

# ---------------------------------------------------------------------------
# Optionally create a dedicated venv
# ---------------------------------------------------------------------------
if $USE_VENV; then
  info "Creating virtualenv at ${VENV_DIR}..."
  python3 -m venv "$VENV_DIR"
  # shellcheck disable=SC1091
  source "$VENV_DIR/bin/activate"
  PIP="$VENV_DIR/bin/pip"
  info "Virtualenv activated."
elif $GLOBAL; then
  PIP="pip3"
else
  PIP="pip3"
fi

# ---------------------------------------------------------------------------
# Install the package
# ---------------------------------------------------------------------------
info "Installing mem-ai from ${SCRIPT_DIR}..."

cd "$SCRIPT_DIR"

if $GLOBAL; then
  $PIP install . --quiet
else
  $PIP install -e . --quiet
fi

success "mem-ai installed successfully!"

# ---------------------------------------------------------------------------
# Create config directory
# ---------------------------------------------------------------------------
mkdir -p "$CONFIG_DIR"
info "Config directory: ${CONFIG_DIR}"

# Write a default config if none exists
CONFIG_FILE="$CONFIG_DIR/config.json"
if [ ! -f "$CONFIG_FILE" ]; then
  cat > "$CONFIG_FILE" <<'JSON'
{
  "api_url": "http://localhost:8000",
  "token": "",
  "platform": "cli",
  "default_provider": "claude",
  "full_context_baseline_tokens": 15000,
  "default_max_tokens": 800
}
JSON
  info "Default config written to ${CONFIG_FILE}"
fi

# ---------------------------------------------------------------------------
# Add venv/bin to PATH hint (if using venv)
# ---------------------------------------------------------------------------
if $USE_VENV; then
  warn "To use mem-ai from any terminal, add the following to your shell rc:"
  echo ""
  echo "  export PATH=\"\$HOME/.mem-ai/venv/bin:\$PATH\""
  echo ""
fi

# ---------------------------------------------------------------------------
# Verify the installation
# ---------------------------------------------------------------------------
if command -v mem-ai &>/dev/null; then
  MEM_AI_BIN=$(command -v mem-ai)
  success "mem-ai is ready: ${MEM_AI_BIN}"
else
  warn "mem-ai not yet on PATH. You may need to restart your terminal."
fi

# ---------------------------------------------------------------------------
# Print quick-start guide
# ---------------------------------------------------------------------------
cat <<EOF

${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${RESET}
${GREEN}  mem-ai — Quick Start${RESET}
${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${RESET}

  1. Start the memory layer backend:
       cd ../  &&  docker compose up -d

  2. Authenticate:
       mem-ai auth login

  3. Ask anything:
       mem-ai ask "How do I configure pgvector?" --provider claude
       mem-ai ask "Summarize my project" --provider openai
       mem-ai ask "Explain this function" --provider gemini
       mem-ai ask "Write a test" --provider ollama --model llama3

  4. Search your memories:
       mem-ai search "React hooks"

  5. View cost savings:
       mem-ai stats

  6. Install shell hooks (optional):
       mem-ai install-hooks

  7. Use with Claude Code (MCP):
       Add to .claude/settings.json:
       {
         "mcpServers": {
           "memory": {
             "command": "python",
             "args": ["-m", "mem_ai.mcp_server"],
             "env": {
               "MEM_AI_API_URL": "http://localhost:8000",
               "MEM_AI_TOKEN": "\${MEM_AI_TOKEN}"
             }
           }
         }
       }

${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${RESET}
EOF
