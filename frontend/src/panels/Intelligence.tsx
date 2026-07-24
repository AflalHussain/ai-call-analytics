import { Card, Legend, RankList } from "../components";
import type { Churn, GapRow, Sentiment, UpsellRow } from "../api";
import { clockTime, fmtInt } from "../api";

const UPSELL_LABEL: Record<string, string> = {
  fibre_upgrade: "Fibre upgrade",
  data_addon: "Data add-on",
  postpaid_migration: "Prepaid → postpaid",
  peo_tv_bundle: "PEO TV bundle",
  roaming_pack: "Roaming pack",
};

const SIGNAL_LABEL: Record<string, string> = {
  mentioned_competitor: "mentioned a competitor",
  asked_about_disconnection: "asked about disconnection",
  threatened_to_leave: "threatened to leave",
  repeat_unresolved_issue: "repeat unresolved issue",
  price_complaint: "price complaint",
  asked_for_contract_end_date: "asked for contract end date",
};

/* -------------------------------------------------------------- dumbbell -- */

/**
 * Sentiment start → end, per reason for calling.
 *
 * A dumbbell rather than paired bars: the quantity that matters is the *travel*
 * between two points on one scale, and a dumbbell encodes that as literal
 * distance. Two bars would make the reader do the subtraction themselves.
 */
function SentimentDumbbell({ data }: { data: Sentiment }) {
  const pos = (v: number) => ((v + 1) / 2) * 100;

  return (
    <div className="dumb">
      {data.by_intent.map((d) => {
        const a = pos(d.avg_start);
        const b = pos(d.avg_end);
        const left = Math.min(a, b);
        const width = Math.abs(b - a);
        return (
          <div className="dumb-row" key={d.intent}>
            <span className="name" title={d.label}>{d.label}</span>
            <div className="dumb-track">
              <span className="axis0" style={{ left: "50%" }} />
              <span className="bar" style={{ left: `${left}%`, width: `${width}%` }} />
              <span className="pt start" style={{ left: `${a}%` }} title={`starts ${d.avg_start}`} />
              <span className="pt end" style={{ left: `${b}%` }} title={`ends ${d.avg_end}`} />
            </div>
            <span className="val">+{d.delta.toFixed(2)}</span>
          </div>
        );
      })}
    </div>
  );
}

/* ---------------------------------------------------------------- panel -- */

export function Intelligence({
  sentiment, churn, gaps, upsell,
}: {
  sentiment: Sentiment;
  churn: Churn;
  gaps: GapRow[];
  upsell: UpsellRow[];
}) {
  return (
    <div className="grid g-6">
      <Card
        className="span-3"
        title="Does the call end better than it started?"
        sub={`Sentiment moves from ${sentiment.avg_start} to ${sentiment.avg_end} on average — ${sentiment.improved_pct}% of calls end more positively than they began`}
      >
        <SentimentDumbbell data={sentiment} />
        <div style={{ marginTop: 14 }}>
          <Legend
            items={[
              { label: "Sentiment at call start", color: "var(--series-2)" },
              { label: "Sentiment at call end", color: "var(--series-1)" },
            ]}
          />
        </div>
        <div className="card-note">
          Scale runs −1 (angry) to +1 (happy); the vertical rule marks neutral.
          The gap between the two dots is de-escalation.
        </div>
      </Card>

      <Card
        className="span-3"
        title="Customers at risk of leaving"
        sub={`${fmtInt(churn.total)} calls carried a churn signal — a retention callback queue, generated automatically`}
        right={<span className="chip">{fmtInt(churn.calls.length)} most recent</span>}
      >
        {churn.top_signals.length > 0 && (
          <div style={{ display: "flex", gap: 6, flexWrap: "wrap", marginBottom: 12 }}>
            {churn.top_signals.slice(0, 4).map((s) => (
              <span className="chip" key={s.signal}>
                {SIGNAL_LABEL[s.signal] ?? s.signal} · {fmtInt(s.total)}
              </span>
            ))}
          </div>
        )}
        <div className="feed">
          {churn.calls.slice(0, 12).map((c) => (
            <div className="feed-row" key={c.call_id}>
              <span className="when">{clockTime(c.started_at)}</span>
              <div className="main">
                <div className="t1">
                  <b>{c.label}</b>
                  <span className="chip">{c.district}</span>
                  <span className="tag churn">churn risk</span>
                </div>
                <div className="t2">
                  {c.churn_signals.map((s) => SIGNAL_LABEL[s] ?? s).join(" · ")}
                </div>
              </div>
            </div>
          ))}
          {churn.calls.length === 0 && <div className="empty">No churn signals in this period.</div>}
        </div>
      </Card>

      <Card
        className="span-4"
        title="What the agent could not answer"
        sub="Ranked by how often it came up — your next-quarter content backlog, written by your customers"
      >
        <RankList
          rows={gaps.slice(0, 8).map((g) => ({
            key: g.question,
            text: g.question,
            n: g.total,
            sub: `most often during: ${g.label}`,
          }))}
          color="var(--series-4)"
        />
      </Card>

      <Card
        className="span-2"
        title="Revenue signals"
        sub="Upsell openings detected in conversation"
      >
        <RankList
          rows={upsell.map((u) => ({
            key: u.opportunity,
            text: UPSELL_LABEL[u.opportunity] ?? u.opportunity,
            n: u.total,
          }))}
          color="var(--series-3)"
        />
        <div className="card-note">
          Detected from what the customer said, not from a campaign list — these
          are people who raised the need themselves.
        </div>
      </Card>
    </div>
  );
}
