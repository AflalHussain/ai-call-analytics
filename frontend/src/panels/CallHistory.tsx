import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  INTENTS, fetchCallDetail, fetchCalls, fmtDuration, fmtInt, timeAgo,
  type CallDetail, type CallFilters, type CallRow,
} from "../api";

const PAGE = 50;

const OUTCOMES = [
  { value: "", label: "All outcomes" },
  { value: "resolved", label: "Resolved" },
  { value: "escalated", label: "Escalated" },
  { value: "abandoned", label: "Abandoned" },
  { value: "transferred", label: "Transferred" },
  { value: "unresolved", label: "Unresolved" },
];
const SENTIMENTS = [
  { value: "", label: "All sentiment" },
  { value: "positive", label: "Positive" },
  { value: "neutral", label: "Neutral" },
  { value: "negative", label: "Negative" },
];
const LANGUAGES = [
  { value: "", label: "All languages" },
  { value: "si", label: "Sinhala" },
  { value: "ta", label: "Tamil" },
  { value: "en", label: "English" },
];

function Badge({ label, status }: { label: string; status: string }) {
  if (label === "—") return <span className="csat-none">—</span>;
  return <span className={`badge s-${status}`}>{label}</span>;
}

/* --------------------------------------------------------------- drawer -- */

function DetailDrawer({ callId, onClose }: { callId: string; onClose: () => void }) {
  const [detail, setDetail] = useState<CallDetail | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setDetail(null);
    fetchCallDetail(callId)
      .then((d) => { if (!cancelled) { setDetail(d); setLoading(false); } })
      .catch(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, [callId]);

  // Close on Escape — expected for a right-drawer.
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  return (
    <>
      <div className="drawer-scrim" onClick={onClose} />
      <aside className="drawer" role="dialog" aria-label="Call detail">
        <div className="drawer-head">
          <div className="drawer-title">
            <h3>{detail?.customer_ref ?? "…"}</h3>
            {detail && (
              <span className="drawer-sub">
                {detail.service} · {detail.language} · {detail.short_id}
              </span>
            )}
          </div>
          <button className="drawer-close" onClick={onClose}>Close</button>
        </div>

        {loading && <div className="empty">Loading…</div>}

        {detail && (
          <div className="drawer-body">
            <div className="drawer-meta">
              <div><span>Outcome</span><Badge label={detail.outcome} status={detail.outcome_status} /></div>
              <div><span>Sentiment</span><Badge label={detail.sentiment} status={detail.sentiment_status} /></div>
              <div><span>Duration</span><b>{fmtDuration(detail.duration_sec)}</b></div>
              <div><span>CSAT</span><b>{detail.csat != null ? detail.csat.toFixed(1) : "—"}</b></div>
              {detail.district && <div><span>District</span><b>{detail.district}</b></div>}
              {detail.customer_segment && <div><span>Segment</span><b style={{ textTransform: "capitalize" }}>{detail.customer_segment}</b></div>}
            </div>

            <div className="drawer-section">
              <h4>Call summary</h4>
              <p>{detail.summary}</p>
            </div>

            {detail.key_points.length > 0 && (
              <div className="drawer-section">
                <h4>Key points</h4>
                <ul className="keypoints">
                  {detail.key_points.map((k, i) => <li key={i}>{k}</li>)}
                </ul>
              </div>
            )}

            {detail.churn_risk && (
              <div className="drawer-flag">⚠ Flagged for retention follow-up</div>
            )}
          </div>
        )}
      </aside>
    </>
  );
}

/* ---------------------------------------------------------------- panel -- */

export function CallHistory({ range }: { range: { from: string; to: string } }) {
  const [filters, setFilters] = useState<CallFilters>({});
  const [searchInput, setSearchInput] = useState("");
  const [rows, setRows] = useState<CallRow[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(false);
  const [selected, setSelected] = useState<string | null>(null);
  const offsetRef = useRef(0);
  const doneRef = useRef(false);
  const sentinel = useRef<HTMLTableRowElement | null>(null);

  // Debounce the search box so we don't fire a request per keystroke.
  useEffect(() => {
    const t = setTimeout(
      () => setFilters((f) => ({ ...f, search: searchInput.trim() || undefined })),
      300,
    );
    return () => clearTimeout(t);
  }, [searchInput]);

  const filterKey = useMemo(
    () => JSON.stringify([range.from, range.to, filters]),
    [range.from, range.to, filters],
  );

  const loadPage = useCallback(async (reset: boolean) => {
    if (loading) return;
    if (!reset && doneRef.current) return;
    setLoading(true);
    const offset = reset ? 0 : offsetRef.current;
    try {
      const page = await fetchCalls(range, filters, PAGE, offset);
      setTotal(page.total);
      offsetRef.current = offset + page.calls.length;
      doneRef.current = offsetRef.current >= page.total;
      setRows((prev) => (reset ? page.calls : [...prev, ...page.calls]));
    } finally {
      setLoading(false);
    }
  }, [range, filters, loading]);

  // Reset and reload whenever range or filters change.
  useEffect(() => {
    offsetRef.current = 0;
    doneRef.current = false;
    setRows([]);
    loadPage(true);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [filterKey]);

  // Infinite scroll: load the next page when the sentinel row scrolls into view.
  useEffect(() => {
    const el = sentinel.current;
    if (!el) return;
    const io = new IntersectionObserver(
      (entries) => { if (entries[0].isIntersecting) loadPage(false); },
      { rootMargin: "300px" },
    );
    io.observe(el);
    return () => io.disconnect();
  }, [loadPage]);

  const set = (k: keyof CallFilters) => (e: React.ChangeEvent<HTMLSelectElement>) =>
    setFilters((f) => ({ ...f, [k]: e.target.value || undefined }));

  return (
    <div className="section">
      <div className="ch-head">
        <div>
          <h2 className="ch-title">Call History</h2>
          <span className="ch-count">{fmtInt(total)} calls in range</span>
        </div>
      </div>

      <div className="ch-controls">
        <input
          className="ch-search"
          placeholder="Search by call ID…"
          value={searchInput}
          onChange={(e) => setSearchInput(e.target.value)}
        />
        <select value={filters.outcome ?? ""} onChange={set("outcome")}>
          {OUTCOMES.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
        </select>
        <select value={filters.sentiment ?? ""} onChange={set("sentiment")}>
          {SENTIMENTS.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
        </select>
        <select value={filters.language ?? ""} onChange={set("language")}>
          {LANGUAGES.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
        </select>
        <select value={filters.service ?? ""} onChange={set("service")}>
          <option value="">All services</option>
          {INTENTS.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
        </select>
      </div>

      <div className="card ch-tablewrap">
        <div className="scroll-x">
          <table className="ch-table">
            <thead>
              <tr>
                <th>Time</th>
                <th>Customer</th>
                <th>Service</th>
                <th>Language</th>
                <th>Duration</th>
                <th>Outcome</th>
                <th>Sentiment</th>
                <th>CSAT</th>
                <th aria-label="Summary" />
              </tr>
            </thead>
            <tbody>
              {rows.map((r) => (
                <tr
                  key={r.call_id}
                  className={`ch-row${selected === r.call_id ? " sel" : ""}`}
                  onClick={() => setSelected(r.call_id)}
                >
                  <td className="muted">{timeAgo(r.started_at)}</td>
                  <td className="strong">
                    {r.customer_ref}
                    {r.churn_risk && <span className="risk-dot" title="Retention risk" />}
                  </td>
                  <td>{r.service}</td>
                  <td>{r.language}</td>
                  <td className="tnum">{fmtDuration(r.duration_sec)}</td>
                  <td><Badge label={r.outcome} status={r.outcome_status} /></td>
                  <td><Badge label={r.sentiment} status={r.sentiment_status} /></td>
                  <td className="tnum">{r.csat != null ? r.csat.toFixed(1) : <span className="csat-none">—</span>}</td>
                  <td><span className="ch-summary-link">Summary</span></td>
                </tr>
              ))}
              {/* Sentinel drives infinite scroll. */}
              <tr ref={sentinel} className="ch-sentinel">
                <td colSpan={9}>
                  {loading ? "Loading…" : rows.length === 0 ? "No calls match these filters." :
                    doneRef.current ? `End of ${fmtInt(total)} calls` : ""}
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>

      {selected && <DetailDrawer callId={selected} onClose={() => setSelected(null)} />}
    </div>
  );
}
