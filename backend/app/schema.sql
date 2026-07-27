-- Call Agent Dashboard schema.
-- Mirrors DATA_CONTRACT.md v0.1. Safe to re-run.

-- digest() for the searchable customer-ref expression in app/calls.py.
CREATE EXTENSION IF NOT EXISTS pgcrypto;

CREATE TABLE IF NOT EXISTS calls (
    call_id               TEXT PRIMARY KEY,

    -- timing
    started_at            TIMESTAMPTZ NOT NULL,
    ended_at              TIMESTAMPTZ,
    duration_sec          INTEGER     NOT NULL,
    ai_handling_sec       INTEGER,
    queue_wait_sec        INTEGER,

    -- caller
    caller_hash           TEXT,
    district              TEXT,
    customer_segment      TEXT,
    channel               TEXT,
    -- affected service line the caller keyed in (landline/mobile), or NULL for
    -- account-level calls. Stored in full; the dashboard masks it at render.
    affected_number       TEXT,
    -- number the caller agreed to be called back on, or NULL if no callback was
    -- requested. Shown in full in the summary drawer only, never on the table.
    callback_number       TEXT,
    -- caller's own incoming number (CLI), or NULL if withheld. Raw caller
    -- identity, kept alongside caller_hash; masked in the drawer, never on table.
    caller_number         TEXT,

    -- subject
    intent                TEXT        NOT NULL,
    sub_intent            TEXT,
    topics                TEXT[]      NOT NULL DEFAULT '{}',
    language_primary      TEXT        NOT NULL,
    language_mix          TEXT[]      NOT NULL DEFAULT '{}',

    -- outcome
    handled_by            TEXT        NOT NULL,
    resolved              BOOLEAN     NOT NULL,
    escalation_reason     TEXT,
    actions_taken         JSONB       NOT NULL DEFAULT '[]'::jsonb,

    -- experience
    sentiment_start       REAL,
    sentiment_end         REAL,
    csat_predicted        SMALLINT,
    interruptions         SMALLINT,
    silence_ratio         REAL,

    -- commercial / risk
    churn_risk            BOOLEAN     NOT NULL DEFAULT FALSE,
    churn_signals         TEXT[]      NOT NULL DEFAULT '{}',
    upsell_opportunity    TEXT,
    unanswered_questions  TEXT[]      NOT NULL DEFAULT '{}',

    -- provenance
    summary               TEXT,
    enrichment_model      TEXT,
    enrichment_confidence REAL,
    schema_version        TEXT        NOT NULL DEFAULT '0.1',
    ingested_at           TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Idempotent for databases created before affected_number existed.
ALTER TABLE calls ADD COLUMN IF NOT EXISTS affected_number TEXT;
ALTER TABLE calls ADD COLUMN IF NOT EXISTS callback_number TEXT;
ALTER TABLE calls ADD COLUMN IF NOT EXISTS caller_number TEXT;

CREATE INDEX IF NOT EXISTS calls_started_at_idx    ON calls (started_at DESC);
CREATE INDEX IF NOT EXISTS calls_intent_idx        ON calls (intent);
CREATE INDEX IF NOT EXISTS calls_district_idx      ON calls (district);
CREATE INDEX IF NOT EXISTS calls_handled_by_idx    ON calls (handled_by);
CREATE INDEX IF NOT EXISTS calls_caller_hash_idx   ON calls (caller_hash, started_at);
-- drives the emerging-issue spike query
CREATE INDEX IF NOT EXISTS calls_spike_idx         ON calls (intent, district, started_at DESC);
-- partial index: the churn feed only ever reads flagged rows
CREATE INDEX IF NOT EXISTS calls_churn_idx         ON calls (started_at DESC) WHERE churn_risk;
CREATE INDEX IF NOT EXISTS calls_topics_gin_idx    ON calls USING GIN (topics);


-- Operational settings. Single row, id = 1. Business hours drive the
-- "answered outside office hours" KPI; timezone anchors the daily/heatmap
-- aggregates to Sri Lanka local time.
CREATE TABLE IF NOT EXISTS config (
    id                       SMALLINT PRIMARY KEY DEFAULT 1 CHECK (id = 1),
    business_hours_start     TIME    NOT NULL DEFAULT '08:30',
    business_hours_end       TIME    NOT NULL DEFAULT '17:30',
    timezone                 TEXT    NOT NULL DEFAULT 'Asia/Colombo'
);

INSERT INTO config (id) VALUES (1) ON CONFLICT (id) DO NOTHING;

-- Drop columns from pre-existing DBs. The baseline_* columns backed the removed
-- "Compare to current contact centre" toggle; the cost/currency/flag columns
-- backed the removed "Agent cost avoided" money tile.
ALTER TABLE config DROP COLUMN IF EXISTS human_baseline_aht_sec;
ALTER TABLE config DROP COLUMN IF EXISTS baseline_containment_pct;
ALTER TABLE config DROP COLUMN IF EXISTS baseline_abandon_pct;
ALTER TABLE config DROP COLUMN IF EXISTS baseline_csat;
ALTER TABLE config DROP COLUMN IF EXISTS agent_cost_per_hour_lkr;
ALTER TABLE config DROP COLUMN IF EXISTS currency;
ALTER TABLE config DROP COLUMN IF EXISTS figures_are_client_supplied;


-- Emerging-issue alerts, written by app/alerts.py.
CREATE TABLE IF NOT EXISTS alerts (
    id            BIGSERIAL PRIMARY KEY,
    detected_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    kind          TEXT NOT NULL,              -- intent_district_spike | topic_spike
    intent        TEXT,
    district      TEXT,
    topic         TEXT,
    window_count  INTEGER NOT NULL,
    baseline_mean REAL    NOT NULL,
    baseline_std  REAL    NOT NULL,
    z_score       REAL    NOT NULL,
    pct_change    REAL    NOT NULL,
    severity      TEXT    NOT NULL,           -- critical | warning
    headline      TEXT    NOT NULL,
    dedupe_key    TEXT    NOT NULL,
    -- Signals folded into this alert because they describe the same incident.
    corroborating TEXT[]  NOT NULL DEFAULT '{}',
    resolved_at   TIMESTAMPTZ
);

-- Idempotent for databases created before `corroborating` existed.
ALTER TABLE alerts ADD COLUMN IF NOT EXISTS corroborating TEXT[] NOT NULL DEFAULT '{}';

-- One live alert per (kind, intent, district, topic) at a time.
CREATE UNIQUE INDEX IF NOT EXISTS alerts_active_dedupe_idx
    ON alerts (dedupe_key) WHERE resolved_at IS NULL;
CREATE INDEX IF NOT EXISTS alerts_detected_at_idx ON alerts (detected_at DESC);
