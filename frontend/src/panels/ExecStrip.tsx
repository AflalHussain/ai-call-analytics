import { StatTile } from "../components";
import type { Kpis, TimelinePoint } from "../api";
import { fmtDuration, fmtInt } from "../api";

/**
 * Layer 1 — the executive strip.
 *
 * Five absolute figures, each with a context line under it. The headline
 * containment tile spans two columns so the five tiles fill the six-column
 * grid without a gap.
 */
export function ExecStrip({
  kpis, timeline,
}: {
  kpis: Kpis;
  timeline: TimelinePoint[];
}) {
  const spark = (key: keyof TimelinePoint) =>
    timeline.map((t) => ({ day: t.day, v: Number(t[key]) }));

  return (
    <div className="grid g-6">
      <StatTile
        hero
        wide
        label="Calls handled end-to-end by AI"
        value={`${kpis.containment_pct}`}
        unit="%"
        spark={spark("containment_pct")}
        foot={<span>{fmtInt(kpis.ai_handled)} of {fmtInt(kpis.total_calls)} calls</span>}
      />

      <StatTile
        label="Avg handling time"
        value={fmtDuration(kpis.avg_ai_duration_sec)}
        foot={<span>AI-handled calls</span>}
      />

      <StatTile
        label="Answered outside office hours"
        value={`${kpis.after_hours_pct}`}
        unit="%"
        foot={<span>{fmtInt(kpis.after_hours_calls)} calls — currently unanswered</span>}
      />

      <StatTile
        label="Predicted CSAT"
        hint="Predicted from call content — sentiment and resolution. Not a customer survey; covers 100% of calls."
        value={kpis.avg_csat.toFixed(2)}
        unit="/5"
        spark={spark("avg_csat")}
        foot={<span>across {fmtInt(kpis.total_calls)} calls</span>}
      />

      <StatTile
        label="Abandoned before answer"
        value={`${kpis.abandon_pct}`}
        unit="%"
        foot={<span>{fmtInt(kpis.abandoned)} calls</span>}
      />
    </div>
  );
}
