"""FastAPI app — analytics endpoints, ingest, and the SSE stream."""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone

from fastapi import FastAPI, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse

from . import alerts, config, db, events, ingest, queries
from .models import CallBatch, CallRecord, ConfigPatch

DEFAULT_RANGE_DAYS = 30


@asynccontextmanager
async def lifespan(app: FastAPI):
    await db.connect()
    await db.apply_schema()
    yield
    await db.disconnect()


app = FastAPI(title="AI Call Agent — Analytics API", version="0.1.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # demo only — lock down before anything real
    allow_methods=["*"],
    allow_headers=["*"],
)


def _range(frm: str | None, to: str | None) -> tuple[datetime, datetime]:
    """Parse the shared date range. Defaults to the trailing 30 days."""
    end = datetime.fromisoformat(to) if to else datetime.now(timezone.utc)
    start = datetime.fromisoformat(frm) if frm else end - timedelta(days=DEFAULT_RANGE_DAYS)
    if start.tzinfo is None:
        start = start.replace(tzinfo=timezone.utc)
    if end.tzinfo is None:
        end = end.replace(tzinfo=timezone.utc)
    return start, end


Frm = Query(None, alias="from")
To = Query(None, alias="to")


# --------------------------------------------------------------------------
# Ingest
# --------------------------------------------------------------------------

@app.post("/ingest/call", status_code=202)
async def ingest_call(payload: CallRecord | CallBatch):
    calls = payload.calls if isinstance(payload, CallBatch) else [payload]
    written = await ingest.store(calls)
    # A live call can itself be the thing that trips an alert.
    found = await alerts.detect(persist=True)
    if found:
        events.publish("alert", found[0])
    return {"accepted": written}


# --------------------------------------------------------------------------
# Analytics
# --------------------------------------------------------------------------

@app.get("/api/kpis")
async def get_kpis(frm: str | None = Frm, to: str | None = To):
    return await queries.kpis(*_range(frm, to))


@app.get("/api/timeline")
async def get_timeline(frm: str | None = Frm, to: str | None = To):
    return await queries.timeline(*_range(frm, to))


@app.get("/api/volume")
async def get_volume(frm: str | None = Frm, to: str | None = To):
    return await queries.volume_heatmap(*_range(frm, to))


@app.get("/api/intents")
async def get_intents(frm: str | None = Frm, to: str | None = To):
    return await queries.intents(*_range(frm, to))


@app.get("/api/escalations")
async def get_escalations(frm: str | None = Frm, to: str | None = To):
    return await queries.escalations(*_range(frm, to))


@app.get("/api/languages")
async def get_languages(frm: str | None = Frm, to: str | None = To):
    return await queries.languages(*_range(frm, to))


@app.get("/api/sentiment")
async def get_sentiment(frm: str | None = Frm, to: str | None = To):
    return await queries.sentiment(*_range(frm, to))


@app.get("/api/churn")
async def get_churn(frm: str | None = Frm, to: str | None = To):
    return await queries.churn_feed(*_range(frm, to))


@app.get("/api/knowledge-gaps")
async def get_knowledge_gaps(frm: str | None = Frm, to: str | None = To):
    return await queries.knowledge_gaps(*_range(frm, to))


@app.get("/api/upsell")
async def get_upsell(frm: str | None = Frm, to: str | None = To):
    return await queries.upsell(*_range(frm, to))


@app.get("/api/alerts")
async def get_alerts():
    return await alerts.active_alerts()


# --------------------------------------------------------------------------
# Config (the ROI inputs)
# --------------------------------------------------------------------------

@app.get("/api/config")
async def get_config():
    return await config.get_config()


@app.patch("/api/config")
async def patch_config(patch: ConfigPatch):
    return await config.patch_config(patch.model_dump(exclude_none=True))


# --------------------------------------------------------------------------
# Live stream
# --------------------------------------------------------------------------

@app.get("/api/stream")
async def stream(request: Request):
    q = events.subscribe()

    async def gen():
        try:
            yield "event: ready\ndata: {}\n\n"
            while True:
                if await request.is_disconnected():
                    break
                try:
                    yield await asyncio.wait_for(q.get(), timeout=15)
                except asyncio.TimeoutError:
                    # Heartbeat — keeps proxies from closing an idle connection.
                    yield ": keepalive\n\n"
        finally:
            events.unsubscribe(q)

    return StreamingResponse(
        gen(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.get("/health")
async def health():
    async with db.pool().acquire() as conn:
        calls = await conn.fetchval("SELECT count(*) FROM calls")
        newest = await conn.fetchval("SELECT max(started_at) FROM calls")
    return {
        "ok": True,
        "calls": calls,
        "newest_call": newest.isoformat() if newest else None,
        "sse_clients": events.subscriber_count(),
    }
