import { useCallback, useEffect, useRef, useState } from "react";

// ---------------------------------------------------------------- types --

export interface Kpis {
  total_calls: number;
  ai_handled: number;
  escalated: number;
  abandoned: number;
  containment_pct: number;
  resolution_pct: number;
  avg_ai_duration_sec: number;
  after_hours_calls: number;
  after_hours_pct: number;
  after_hours_handled: number;
  avg_csat: number;
  avg_sentiment_end: number;
  avg_sentiment_delta: number;
  abandon_pct: number;
  repeat_caller_pct: number;
  churn_flagged: number;
}

export interface TimelinePoint {
  day: string; calls: number; contained: number;
  containment_pct: number; avg_csat: number; sentiment_delta: number;
}
export interface VolumeCell { dow: number; hour: number; calls: number; contained: number }
export interface IntentRow {
  intent: string; label: string; total: number; contained: number; escalated: number;
  containment_pct: number; avg_duration_sec: number; sentiment_delta: number; avg_csat: number;
}
export interface EscalationRow { reason: string; label: string; total: number; share_pct: number }
export interface LanguageRow {
  lang: string; label: string; total: number; contained: number;
  containment_pct: number; avg_csat: number; code_switched: number;
}
export interface Languages {
  by_language: LanguageRow[];
  by_district: { district: string; si: number; ta: number; en: number }[];
}
export interface Sentiment {
  avg_start: number; avg_end: number; delta: number;
  improved_pct: number; worsened_pct: number;
  by_intent: { intent: string; label: string; avg_start: number; avg_end: number; delta: number; total: number }[];
}
export interface ChurnCall {
  call_id: string; started_at: string; district: string; intent: string; label: string;
  customer_segment: string; churn_signals: string[]; sentiment_end: number;
  summary: string; handled_by: string;
}
export interface Churn {
  total: number;
  top_signals: { signal: string; total: number }[];
  calls: ChurnCall[];
}
export interface GapRow { question: string; total: number; intent: string; label: string }
export interface UpsellRow { opportunity: string; total: number; contained: number }
export interface Alert {
  id: number; detected_at: string; kind: string;
  intent: string | null; district: string | null; topic: string | null;
  window_count: number; baseline_mean: number; z_score: number; pct_change: number;
  severity: "critical" | "warning"; headline: string; corroborating: string[];
}
export interface CallRow {
  call_id: string;
  customer_ref: string;
  started_at: string;
  duration_sec: number;
  service: string;
  intent: string;
  district: string | null;
  language: string;
  language_code: string;
  outcome: string;
  outcome_status: string;
  sentiment: string;
  sentiment_status: string;
  csat: number | null;
  churn_risk: boolean;
}
export interface CallsPage { total: number; calls: CallRow[]; limit: number; offset: number }
export interface CallDetail {
  call_id: string; customer_ref: string; short_id: string; started_at: string;
  duration_sec: number; service: string; district: string | null;
  customer_segment: string | null; language: string; languages: string[];
  outcome: string; outcome_status: string; sentiment: string; sentiment_status: string;
  sentiment_start: number | null; sentiment_end: number | null; csat: number | null;
  churn_risk: boolean; summary: string; key_points: string[];
}

export interface LiveCall {
  call_id: string; started_at: string; intent: string; label: string;
  district: string | null; language: string; handled_by: string;
  resolved: boolean; duration_sec: number;
  sentiment_start: number | null; sentiment_end: number | null;
  churn_risk: boolean; summary: string | null;
}

// ----------------------------------------------------------------- fetch --

async function get<T>(path: string, range?: { from: string; to: string }): Promise<T> {
  const qs = range ? `?from=${encodeURIComponent(range.from)}&to=${encodeURIComponent(range.to)}` : "";
  const r = await fetch(`/api${path}${qs}`);
  if (!r.ok) throw new Error(`${path} -> ${r.status}`);
  return r.json();
}

/** One fetch hook, re-run whenever the shared date range or a refresh tick changes. */
export function useApi<T>(path: string, range: { from: string; to: string } | null, tick = 0) {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    get<T>(path, range ?? undefined)
      .then((d) => { if (!cancelled) { setData(d); setError(null); } })
      .catch((e) => { if (!cancelled) setError(String(e)); });
    return () => { cancelled = true; };
  }, [path, range?.from, range?.to, tick]);

  return { data, error };
}

export interface CallFilters {
  search?: string; outcome?: string; sentiment?: string;
  language?: string; service?: string;
}

export async function fetchCalls(
  range: { from: string; to: string },
  filters: CallFilters,
  limit: number,
  offset: number,
): Promise<CallsPage> {
  const p = new URLSearchParams({
    from: range.from, to: range.to,
    limit: String(limit), offset: String(offset),
  });
  for (const [k, v] of Object.entries(filters)) if (v) p.set(k, v);
  const r = await fetch(`/api/calls?${p.toString()}`);
  if (!r.ok) throw new Error(`/api/calls -> ${r.status}`);
  return r.json();
}

export async function fetchCallDetail(callId: string): Promise<CallDetail> {
  const r = await fetch(`/api/calls/${encodeURIComponent(callId)}`);
  if (!r.ok) throw new Error(`/api/calls/${callId} -> ${r.status}`);
  return r.json();
}

export async function patchConfig(patch: Record<string, unknown>) {
  const r = await fetch("/api/config", {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(patch),
  });
  return r.json();
}

// ------------------------------------------------------------------- SSE --

/**
 * Live call feed. SSE rather than WebSocket: the traffic is one-directional and
 * EventSource survives corporate proxies that mangle WebSocket upgrades — which
 * matters when the demo runs on someone else's network.
 */
export function useLiveFeed(max = 25) {
  const [calls, setCalls] = useState<LiveCall[]>([]);
  const [connected, setConnected] = useState(false);
  const [bump, setBump] = useState(0);
  const seen = useRef<Set<string>>(new Set());

  useEffect(() => {
    const es = new EventSource("/api/stream");
    es.addEventListener("ready", () => setConnected(true));
    es.addEventListener("call", (e) => {
      const call: LiveCall = JSON.parse((e as MessageEvent).data);
      if (seen.current.has(call.call_id)) return;
      seen.current.add(call.call_id);
      setCalls((prev) => [call, ...prev].slice(0, max));
      // Nudge every panel to refetch — a live call changes the aggregates too,
      // which is the point of the moment.
      setBump((n) => n + 1);
    });
    es.addEventListener("alert", () => setBump((n) => n + 1));
    es.onerror = () => setConnected(false);
    return () => es.close();
  }, [max]);

  const clear = useCallback(() => setCalls([]), []);
  return { calls, connected, bump, clear };
}

// ------------------------------------------------------------- formatting --

export const fmtInt = (n: number) => n.toLocaleString("en-US");

export function fmtDuration(sec: number) {
  const m = Math.floor(sec / 60);
  const s = Math.round(sec % 60);
  return m > 0 ? `${m}m ${s.toString().padStart(2, "0")}s` : `${s}s`;
}

export function timeAgo(iso: string) {
  const diff = (Date.now() - new Date(iso).getTime()) / 1000;
  if (diff < 60) return "just now";
  if (diff < 3600) return `${Math.floor(diff / 60)}m ago`;
  if (diff < 86400) return `${Math.floor(diff / 3600)}h ago`;
  return `${Math.floor(diff / 86400)}d ago`;
}

export function clockTime(iso: string) {
  return new Date(iso).toLocaleTimeString("en-GB", { hour: "2-digit", minute: "2-digit" });
}

export const LANG_LABEL: Record<string, string> = { si: "Sinhala", ta: "Tamil", en: "English" };

/** Intent value → label, mirroring backend INTENT_LABELS. Drives the Service filter. */
export const INTENTS: { value: string; label: string }[] = [
  { value: "bill_inquiry", label: "Bill inquiry" },
  { value: "bill_payment", label: "Bill payment" },
  { value: "reload_topup", label: "Reload / top-up" },
  { value: "data_package", label: "Data package" },
  { value: "data_balance", label: "Data balance" },
  { value: "broadband_fault", label: "Broadband fault" },
  { value: "broadband_speed", label: "Broadband speed" },
  { value: "router_wifi", label: "Router / WiFi" },
  { value: "mobile_coverage", label: "Mobile coverage" },
  { value: "sim_services", label: "SIM services" },
  { value: "roaming", label: "Roaming" },
  { value: "peo_tv", label: "PEO TV" },
  { value: "new_connection", label: "New connection" },
  { value: "package_change", label: "Package change" },
  { value: "disconnection", label: "Disconnection" },
  { value: "complaint_followup", label: "Complaint follow-up" },
  { value: "general_info", label: "General info" },
  { value: "other", label: "Other" },
];
