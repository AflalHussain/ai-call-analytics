import { StatTile } from "../components";
import type { Kpis, TimelinePoint } from "../api";
import { fmtDuration, fmtInt, fmtMoney } from "../api";

/**
 * Layer 1 — the executive / ROI strip.
 *
 * Every tile is a comparison against the client's own baseline, not an absolute.
 * The `compare` toggle exists so the deltas can be flipped on deliberately in
 * front of the CFO rather than being wallpaper.
 */
export function ExecStrip({
  kpis, timeline, compare,
}: {
  kpis: Kpis;
  timeline: TimelinePoint[];
  compare: boolean;
}) {
  const b = kpis.baseline;
  const spark = (key: keyof TimelinePoint) =>
    timeline.map((t) => ({ day: t.day, v: Number(t[key]) }));

  const ahtDeltaPct = b.aht_sec
    ? ((kpis.avg_ai_duration_sec - b.aht_sec) / b.aht_sec) * 100
    : null;

  return (
    <>
      <div className="grid g-6">
        <StatTile
          hero
          label="Calls handled end-to-end by AI"
          value={`${kpis.containment_pct}`}
          unit="%"
          delta={compare ? kpis.containment_pct - b.containment_pct : null}
          deltaLabel={compare ? "vs current contact centre" : undefined}
          deltaDir="good"
          spark={spark("containment_pct")}
          foot={!compare ? <span>{fmtInt(kpis.ai_handled)} of {fmtInt(kpis.total_calls)} calls</span> : undefined}
        />

        <StatTile
          hero
          label="Agent cost avoided"
          value={fmtMoney(kpis.lkr_saved, kpis.currency)}
          foot={<span>{fmtInt(Math.round(kpis.agent_hours_saved))} agent-hours returned</span>}
        />

        <StatTile
          label="Avg handling time"
          value={fmtDuration(kpis.avg_ai_duration_sec)}
          delta={compare && ahtDeltaPct != null ? ahtDeltaPct : null}
          deltaLabel={compare ? `vs ${fmtDuration(b.aht_sec)} human baseline` : undefined}
          deltaDir="good"
          foot={!compare ? <span>AI-handled calls</span> : undefined}
        />

        <StatTile
          label="Answered outside office hours"
          value={`${kpis.after_hours_pct}`}
          unit="%"
          foot={<span>{fmtInt(kpis.after_hours_calls)} calls — currently unanswered</span>}
        />

        <StatTile
          label="Predicted CSAT"
          value={kpis.avg_csat.toFixed(2)}
          unit="/5"
          delta={compare ? kpis.avg_csat - b.csat : null}
          deltaLabel={compare ? `vs ${b.csat.toFixed(1)} baseline` : undefined}
          deltaDir="good"
          spark={spark("avg_csat")}
        />

        <StatTile
          label="Abandoned before answer"
          value={`${kpis.abandon_pct}`}
          unit="%"
          delta={compare ? kpis.abandon_pct - b.abandon_pct : null}
          deltaLabel={compare ? `vs ${b.abandon_pct}% baseline` : undefined}
          deltaDir="good"
          foot={!compare ? <span>{fmtInt(kpis.abandoned)} calls</span> : undefined}
        />
      </div>

      {!kpis.figures_are_client_supplied && (
        <div className="provisional">
          <span>⚠️</span>
          <span>
            <b>Placeholder cost inputs.</b> Agent cost avoided is derived from an
            assumed {kpis.currency}&nbsp;850/hour fully-loaded agent cost and a{" "}
            {fmtDuration(b.aht_sec)} human handling time. Replace these with SLT
            Mobitel's own figures before quoting the number — the calculation is
            live and updates instantly.
          </span>
        </div>
      )}
    </>
  );
}
