#!/bin/bash
# Start the backend (mock mode unless .env says otherwise)
cd "$(dirname "$0")/../apps/api"
exec .venv/bin/python -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
