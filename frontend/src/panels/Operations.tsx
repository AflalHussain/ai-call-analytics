import { Fragment } from "react";
import {
  Bar, BarChart, CartesianGrid, Cell, ReferenceLine,
  ResponsiveContainer, Tooltip, XAxis, YAxis,
} from "recharts";
import { Card, Legend, RankList, Tip } from "../components";
import type { EscalationRow, IntentRow, Languages, VolumeCell } from "../api";
import { fmtDuration, fmtInt } from "../api";
import { useTokens } from "../theme";

const DOW = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"];
const SEQ = ["--seq-0", "--seq-1", "--seq-2", "--seq-3", "--seq-4", "--seq-5", "--seq-6", "--seq-7"];

/* ------------------------------------------------------------- heatmap --- */

function VolumeHeatmap({ cells, businessEnd = 17 }: { cells: VolumeCell[]; businessEnd?: number }) {
  const grid = new Map<string, VolumeCell>();
  cells.forEach((c) => grid.set(`${c.dow}-${c.hour}`, c));
  const max = Math.max(...cells.map((c) => c.calls), 1);

  // Sequential ramp: near-zero recedes toward the surface, magnitude brightens.
  const shade = (n: number) => {
    if (n === 0) return `var(${SEQ[0]})`;
    const i = Math.min(SEQ.length - 1, 1 + Math.floor((n / max) * (SEQ.length - 1.001)));
    return `var(${SEQ[i]})`;
  };

  // Mon-first reads better than the Sun-first the SQL returns.
  const order = [1, 2, 3, 4, 5, 6, 0];

  return (
    <>
      <div className="scroll-x">
        <div className="heat">
          <span />
          {Array.from({ length: 24 }, (_, h) => (
            <span className="hhour" key={`h${h}`}>{h % 3 === 0 ? h : ""}</span>
          ))}
          {order.map((d) => (
            <Fragment key={d}>
              <span className="hlabel">{DOW[d]}</span>
              {Array.from({ length: 24 }, (_, h) => {
                const c = grid.get(`${d}-${h}`);
                const n = c?.calls ?? 0;
                return (
                  <div
                    key={`${d}-${h}`}
                    className="cell"
                    style={{ background: shade(n) }}
                    title={`${DOW[d]} ${String(h).padStart(2, "0")}:00 — ${n} calls${
                      c ? `, ${Math.round((c.contained / Math.max(c.calls, 1)) * 100)}% contained` : ""
                    }`}
                  />
                );
              })}
            </Fragment>
          ))}
        </div>
      </div>
      <div className="heat-legend">
        <span>fewer calls</span>
        <span className="swatches">
          {SEQ.map((s) => <i className="sw" key={s} style={{ background: `var(${s})` }} />)}
        </span>
        <span>more</span>
        <span style={{ marginLeft: "auto" }}>
          Contact centre closes {businessEnd}:30 — the evening peak lands after it
        </span>
      </div>
    </>
  );
}

/* ---------------------------------------------------------------- panel -- */

export function Operations({
  volume, intents, escalations, languages, overallContainment,
}: {
  volume: VolumeCell[];
  intents: IntentRow[];
  escalations: EscalationRow[];
  languages: Languages;
  overallContainment: number;
}) {
  // Worst-first. This chart is meant to be uncomfortable — it is what makes the
  // rest of the page believable, and it doubles as the build roadmap.
  const byContainment = [...intents]
    .filter((i) => i.total >= 40)
    .sort((a, b) => a.containment_pct - b.containment_pct);

  const langTotal = languages.by_language.reduce((s, l) => s + l.total, 0) || 1;

  // Recharts writes SVG presentation attributes; hand it resolved hex, not var().
  const t = useTokens();
  const axis = { stroke: t["--axis"], fontSize: 11.5, tick: { fill: t["--text-muted"] } };

  return (
    <div className="grid g-6">
      <Card
        className="span-4"
        title="When customers call"
        sub="Volume by hour and weekday — the staffing picture"
      >
        <VolumeHeatmap cells={volume} />
      </Card>

      <Card
        className="span-2"
        title="Language mix"
        sub="Sinhala, Tamil and English handled by the same agent"
      >
        <div style={{ display: "flex", flexDirection: "column", gap: 14 }}>
          {languages.by_language.map((l, i) => (
            <div key={l.lang}>
              <div style={{ display: "flex", justifyContent: "space-between", fontSize: 13 }}>
                <span style={{ color: "var(--text-secondary)" }}>{l.label}</span>
                <span style={{ fontVariantNumeric: "tabular-nums" }}>
                  {Math.round((l.total / langTotal) * 100)}%
                </span>
              </div>
              <div style={{ height: 6, background: "var(--surface-2)", borderRadius: 3, marginTop: 5 }}>
                <div
                  style={{
                    width: `${(l.total / langTotal) * 100}%`,
                    height: "100%",
                    borderRadius: 3,
                    background: `var(--series-${i + 1})`,
                  }}
                />
              </div>
              <div style={{ fontSize: 11.5, color: "var(--text-muted)", marginTop: 4 }}>
                {fmtInt(l.total)} calls · {l.containment_pct}% contained · CSAT {l.avg_csat.toFixed(2)}
              </div>
            </div>
          ))}
        </div>
        <div className="card-note">
          Containment holds within {Math.round(
            Math.max(...languages.by_language.map((l) => l.containment_pct)) -
            Math.min(...languages.by_language.map((l) => l.containment_pct))
          )} points across all three languages.{" "}
          {fmtInt(languages.by_language.reduce((s, l) => s + l.code_switched, 0))} calls
          switched language mid-conversation and were still handled.
        </div>
      </Card>

      <Card
        className="span-3"
        title="Containment by reason for calling"
        sub="Where the agent finishes the job — and where it hands off"
      >
        <div style={{ height: Math.max(280, byContainment.length * 25) }}>
          <ResponsiveContainer width="100%" height="100%">
            <BarChart
              layout="vertical"
              data={byContainment}
              margin={{ top: 4, right: 44, bottom: 4, left: 4 }}
              barCategoryGap={5}
            >
              <CartesianGrid stroke={t["--grid"]} horizontal={false} />
              <XAxis type="number" domain={[0, 100]} unit="%" {...axis} />
              <YAxis type="category" dataKey="label" width={116} {...axis} />
              <ReferenceLine
                x={overallContainment}
                stroke={t["--text-muted"]}
                strokeDasharray="3 3"
                label={{ value: "avg", position: "top", fill: t["--text-muted"], fontSize: 11 }}
              />
              <Tooltip
                cursor={{ fill: t["--hover-wash"] }}
                content={({ active, payload }) => {
                  if (!active || !payload?.length) return null;
                  const d = payload[0].payload as IntentRow;
                  return (
                    <Tip
                      title={d.label}
                      rows={[
                        ["Contained", `${d.containment_pct}%`],
                        ["Total calls", fmtInt(d.total)],
                        ["Escalated", fmtInt(d.escalated)],
                        ["Avg duration", fmtDuration(d.avg_duration_sec)],
                      ]}
                    />
                  );
                }}
              />
              <Bar dataKey="containment_pct" radius={[0, 4, 4, 0]} isAnimationActive={false}>
                {byContainment.map((d) => (
                  <Cell
                    key={d.intent}
                    // Status colour, not a series colour: this encodes state
                    // (below/above the line), not identity.
                    fill={d.containment_pct < 55 ? t["--serious"] : t["--series-1"]}
                  />
                ))}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </div>
        <Legend
          items={[
            { label: "At or above target", color: "var(--series-1)" },
            { label: "Below 55% — next to build", color: "var(--serious)" },
          ]}
        />
      </Card>

      <Card
        className="span-2"
        title="Why customers call"
        sub="Ranked by volume"
      >
        <RankList
          rows={intents.slice(0, 10).map((i) => ({
            key: i.intent,
            text: i.label,
            n: i.total,
          }))}
        />
      </Card>

      <Card
        className="span-1"
        title="Why we hand off"
        sub="Escalation reasons"
      >
        <RankList
          rows={escalations.slice(0, 7).map((e) => ({
            key: e.reason,
            text: e.label,
            n: e.total,
            sub: `${e.share_pct}%`,
          }))}
          color="var(--series-2)"
        />
      </Card>
    </div>
  );
}
