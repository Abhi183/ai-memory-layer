#!/usr/bin/env bash
# Quick-start script for local development (no Docker required)
set -e

echo "==> AI Memory Layer — Local Setup"

# 1. Backend
echo ""
echo "── Backend ──────────────────────────────────────────"
cd backend
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

if [ ! -f .env ]; then
  cp .env.example .env
  SECRET=$(python -c "import secrets; print(secrets.token_hex(32))")
  sed -i.bak "s/change-this-to-a-random-32-byte-hex-string/${SECRET}/" .env
  rm -f .env.bak
  echo "Created backend/.env — add your OPENAI_API_KEY if you have one."
fi

cd ..

# 2. Frontend
echo ""
echo "── Frontend ─────────────────────────────────────────"
cd frontend
npm install
cd ..

# 3. Extension
echo ""
echo "── Extension ────────────────────────────────────────"
cd extension
npm install
npm run build
cd ..

echo ""
echo "==> Setup complete!"
echo ""
echo "To start services:"
echo "  docker compose up -d db redis   # start PostgreSQL + Redis only"
echo "  cd backend && uvicorn app.main:app --reload  # API on :8000"
echo "  cd frontend && npm run dev                   # UI on :3000"
echo ""
echo "Or start everything:"
echo "  docker compose up -d"
