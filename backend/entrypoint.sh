#!/bin/sh
# Wait for Postgres, seed the DB if it's empty, then serve the API.
set -e

echo "[entrypoint] waiting for database ..."
python - <<'PY'
import asyncio, os, sys
import asyncpg

url = os.environ["DATABASE_URL"]

async def wait():
    for attempt in range(60):
        try:
            conn = await asyncpg.connect(url)
            await conn.close()
            print("[entrypoint] database is up")
            return
        except Exception as e:  # noqa: BLE001
            print(f"[entrypoint]   not ready ({e.__class__.__name__}); retrying...")
            await asyncio.sleep(1)
    sys.exit("[entrypoint] database never became reachable")

asyncio.run(wait())
PY

# Idempotent: seeds ~4 weeks of data on a fresh volume, skips if already seeded.
echo "[entrypoint] seeding if empty ..."
python scripts/generate_seed.py --if-empty

echo "[entrypoint] starting API on :8000"
exec uvicorn app.main:app --host 0.0.0.0 --port 8000
