import type { ReactNode } from "react";
import { Area, AreaChart, ResponsiveContainer } from "recharts";
import type { Alert } from "./api";
import { fmtInt, timeAgo } from "./api";
import { useTokens } from "./theme";

/* ------------------------------------------------------------------ card -- */

export function Card({
  title, sub, note, right, className = "", children,
}: {
  title?: string; sub?: string; note?: string; right?: ReactNode;
  className?: string; children: ReactNode;
}) {
  return (
    <div className={`card ${className}`}>
      {title && (
        <div className="card-head">
          <h3>{title}</h3>
          {right}
        </div>
      )}
      {sub && <p className="card-sub">{sub}</p>}
      {children}
      {note && <div className="card-note">{note}</div>}
    </div>
  );
}

/* ------------------------------------------------------------- stat tile -- */

export type DeltaDir = "good" | "bad" | "neutral";

/**
 * Delta is always shown against the client's own baseline, never as a bare
 * absolute. A number with nothing to compare it to invites the question
 * "is that good?" — which is the one question we do not want asked on stage.
 */
export function StatTile({
  label, value, unit, delta, deltaLabel, deltaDir = "neutral", spark, hero, foot,
}: {
  label: string;
  value: string | number;
  unit?: string;
  delta?: number | null;
  deltaLabel?: string;
  deltaDir?: DeltaDir;
  spark?: { day: string; v: number }[];
  hero?: boolean;
  foot?: ReactNode;
}) {
  const t = useTokens();
  const cls = delta == null || delta === 0 ? "flat" : deltaDir === "good" ? "up" : deltaDir === "bad" ? "down" : "flat";
  const arrow = delta == null || delta === 0 ? "" : delta > 0 ? "▲" : "▼";
  const gid = `sp-${label.replace(/\W/g, "")}`;

  return (
    <div className={`card tile${hero ? " hero" : ""}`}>
      <span className="label">{label}</span>
      <div className="value">
        {value}
        {unit && <span className="unit">{unit}</span>}
      </div>
      <div className="foot">
        {delta != null && (
          <span className={`delta ${cls}`}>
            {arrow} {Math.abs(delta).toFixed(1)}
            {deltaLabel ? "" : "pp"}
          </span>
        )}
        {deltaLabel && <span>{deltaLabel}</span>}
        {foot}
      </div>
      {spark && spark.length > 1 && (
        <div className="spark">
          <ResponsiveContainer width="100%" height="100%">
            <AreaChart data={spark} margin={{ top: 2, right: 0, bottom: 0, left: 0 }}>
              <defs>
                <linearGradient id={gid} x1="0" y1="0" x2="0" y2="1">
                  <stop offset="0%" stopColor={t["--series-1"]} stopOpacity={0.42} />
                  <stop offset="100%" stopColor={t["--series-1"]} stopOpacity={0} />
                </linearGradient>
              </defs>
              <Area
                type="monotone" dataKey="v" stroke={t["--series-1"]} strokeWidth={2}
                fill={`url(#${gid})`} isAnimationActive={false} dot={false}
              />
            </AreaChart>
          </ResponsiveContainer>
        </div>
      )}
    </div>
  );
}

/* ----------------------------------------------------------- alert card -- */

export function AlertCard({ alert }: { alert: Alert }) {
  const where = alert.district ? ` · ${alert.district}` : "";
  return (
    <div className={`alert ${alert.severity}`}>
      <span className="icon">{alert.severity === "critical" ? "🔴" : "🟠"}</span>
      <div className="body">
        <div className="headline">{alert.headline}</div>
        <div className="meta">
          <span>{fmtInt(alert.window_count)} calls in window{where}</span>
          <span>typical {alert.baseline_mean.toFixed(1)} · {alert.z_score.toFixed(0)}σ above normal</span>
          <span>detected {timeAgo(alert.detected_at)}</span>
          {alert.corroborating.length > 0 && (
            <span>corroborated by: {alert.corroborating.join(", ")}</span>
          )}
        </div>
      </div>
      <span className="sev">{alert.severity}</span>
    </div>
  );
}

/* -------------------------------------------------------------- tooltip -- */

export function Tip({ title, rows }: { title: string; rows: [string, string | number][] }) {
  return (
    <div className="tip">
      <div className="tip-t">{title}</div>
      {rows.map(([k, v]) => (
        <div className="tip-r" key={k}>
          <span>{k}</span>
          <b>{v}</b>
        </div>
      ))}
    </div>
  );
}

/* ----------------------------------------------------------- rank list --- */

/** Horizontal ranked bars. Used where a Recharts axis would waste vertical space. */
export function RankList({
  rows, max, color = "var(--series-1)",
}: {
  rows: { key: string; text: ReactNode; n: number; sub?: string }[];
  max?: number;
  color?: string;
}) {
  const top = max ?? Math.max(...rows.map((r) => r.n), 1);
  return (
    <div className="rank">
      {rows.map((r) => (
        <div key={r.key}>
          <div className="rank-row">
            <span className="txt">{r.text}</span>
            <span className="n">{fmtInt(r.n)}</span>
          </div>
          <div className="rank-bar" style={{ width: `${Math.max(2, (r.n / top) * 100)}%`, background: color }} />
          {r.sub && <div className="rank-sub">{r.sub}</div>}
        </div>
      ))}
    </div>
  );
}

/* --------------------------------------------------------------- legend -- */

export function Legend({ items }: { items: { label: string; color: string }[] }) {
  return (
    <div className="legend">
      {items.map((i) => (
        <span className="k" key={i.label}>
          <i style={{ background: i.color }} />
          {i.label}
        </span>
      ))}
    </div>
  );
}
