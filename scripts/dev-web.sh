#!/bin/bash
# Start the frontend dev server on :3210
cd "$(dirname "$0")/../apps/web"
exec npm run dev
