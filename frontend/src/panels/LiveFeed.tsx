import { Card } from "../components";
import type { LiveCall } from "../api";
import { LANG_LABEL, clockTime, fmtDuration } from "../api";

/**
 * The demo closes on this panel: someone in the room calls the number and
 * watches the call land. Rows flash once on arrival so the moment is visible
 * from the back of the room.
 */
export function LiveFeed({ calls, connected }: { calls: LiveCall[]; connected: boolean }) {
  return (
    <Card
      title="Live calls"
      sub={connected ? "Streaming as calls complete" : "Reconnecting…"}
      right={
        <span className={`live-pill${connected ? "" : " off"}`}>
          <span className="beacon" />
          {connected ? "live" : "offline"}
        </span>
      }
    >
      <div className="feed" style={{ maxHeight: 300 }}>
        {calls.length === 0 && (
          <div className="empty">
            Waiting for the next call.
            <br />
            <span style={{ fontSize: 12 }}>Completed calls appear here within a second.</span>
          </div>
        )}
        {calls.map((c, i) => (
          <div className={`feed-row${i === 0 ? " fresh" : ""}`} key={c.call_id}>
            <span className="when">{clockTime(c.started_at)}</span>
            <div className="main">
              <div className="t1">
                <b>{c.label}</b>
                {c.district && <span className="chip">{c.district}</span>}
                <span className="tag lang">{LANG_LABEL[c.language] ?? c.language}</span>
                <span className={`tag ${c.handled_by === "ai" ? "ai" : c.handled_by === "abandoned" ? "abandoned" : "escalated"}`}>
                  {c.handled_by === "ai" ? "handled by AI" : c.handled_by}
                </span>
                {c.churn_risk && <span className="tag churn">churn risk</span>}
              </div>
              <div className="t2">
                {fmtDuration(c.duration_sec)}
                {c.sentiment_start != null && c.sentiment_end != null && (
                  <> · sentiment {c.sentiment_start.toFixed(2)} → {c.sentiment_end.toFixed(2)}</>
                )}
                {c.summary ? ` · ${c.summary}` : ""}
              </div>
            </div>
          </div>
        ))}
      </div>
    </Card>
  );
}
