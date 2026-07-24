import { useMemo, useState } from "react";
import "./theme.css";
import { AlertCard, Card } from "./components";
import {
  useApi, useLiveFeed,
  type Alert, type Churn, type EscalationRow, type GapRow, type IntentRow,
  type Kpis, type Languages, type Sentiment, type TimelinePoint,
  type UpsellRow, type VolumeCell,
} from "./api";
import { ChartTokenContext, useChartTokens, useTheme } from "./theme";
import { ExecStrip } from "./panels/ExecStrip";
import { Operations } from "./panels/Operations";
import { Intelligence } from "./panels/Intelligence";
import { LiveFeed } from "./panels/LiveFeed";

const RANGES = [
  { key: "7", label: "7 days" },
  { key: "30", label: "30 days" },
  { key: "90", label: "90 days" },
] as const;

export default function App() {
  const [days, setDays] = useState<string>("30");
  const [compare, setCompare] = useState(true);
  const [theme, toggleTheme] = useTheme();
  const tokens = useChartTokens(theme);
  const { calls, connected, bump } = useLiveFeed();

  const range = useMemo(() => {
    const to = new Date();
    const from = new Date(to.getTime() - Number(days) * 864e5);
    return { from: from.toISOString(), to: to.toISOString() };
  }, [days]);

  const kpis = useApi<Kpis>("/kpis", range, bump);
  const timeline = useApi<TimelinePoint[]>("/timeline", range, bump);
  const volume = useApi<VolumeCell[]>("/volume", range, bump);
  const intents = useApi<IntentRow[]>("/intents", range, bump);
  const escalations = useApi<EscalationRow[]>("/escalations", range, bump);
  const languages = useApi<Languages>("/languages", range, bump);
  const sentiment = useApi<Sentiment>("/sentiment", range, bump);
  const churn = useApi<Churn>("/churn", range, bump);
  const gaps = useApi<GapRow[]>("/knowledge-gaps", range, bump);
  const upsell = useApi<UpsellRow[]>("/upsell", range, bump);
  const alerts = useApi<Alert[]>("/alerts", null, bump);

  const err = kpis.error ?? intents.error;

  return (
    <ChartTokenContext.Provider value={tokens}>
    <div className="app">
      <header className="topbar">
        <div className="brand">
          <h1>Call Intelligence</h1>
          <span className="sub">AI customer call handling · SLT Mobitel</span>
        </div>
        <div className="controls">
          <div className="seg" role="group" aria-label="Date range">
            {RANGES.map((r) => (
              <button
                key={r.key}
                aria-pressed={days === r.key}
                onClick={() => setDays(r.key)}
              >
                {r.label}
              </button>
            ))}
          </div>
          <button
            className="toggle"
            aria-pressed={compare}
            onClick={() => setCompare((c) => !c)}
            title="Show every figure as a delta against the current contact centre"
          >
            <span className="dot" />
            Compare to current contact centre
          </button>
          <button
            className="icon-btn"
            onClick={toggleTheme}
            title={`Switch to ${theme === "dark" ? "light" : "dark"} theme`}
            aria-label={`Switch to ${theme === "dark" ? "light" : "dark"} theme`}
          >
            {theme === "dark" ? "☀" : "☾"}
          </button>
        </div>
      </header>

      {err && (
        <div className="provisional" style={{ marginTop: 0 }}>
          <span>⚠️</span>
          <span>
            <b>API unreachable.</b> {err}. Check the backend is running on port 8000.
          </span>
        </div>
      )}

      {/* 1 — Open on what needs attention right now, not on the KPIs. */}
      <section className="section">
        <div className="section-head">
          <h2>Needs attention now</h2>
          <span className="note">
            Detected from call content against a 7-day baseline — no ticket required
          </span>
        </div>
        <div className="grid g-6">
          <div className="span-4" style={{ display: "flex", flexDirection: "column", gap: 12 }}>
            {(alerts.data ?? []).slice(0, 3).map((a) => (
              <AlertCard alert={a} key={a.id} />
            ))}
            {alerts.data?.length === 0 && (
              <Card>
                <div className="empty">No anomalies detected in the last 2 hours.</div>
              </Card>
            )}
          </div>
          <div className="span-2">
            <LiveFeed calls={calls} connected={connected} />
          </div>
        </div>
      </section>

      {/* 2 — The money. */}
      <section className="section">
        <div className="section-head">
          <h2>Business impact</h2>
          <span className="note">Last {days} days</span>
        </div>
        {kpis.data && timeline.data ? (
          <ExecStrip kpis={kpis.data} timeline={timeline.data} compare={compare} />
        ) : (
          <Card><div className="empty">Loading…</div></Card>
        )}
      </section>

      {/* 3 — Where ops will interrogate us. */}
      <section className="section">
        <div className="section-head">
          <h2>Operations</h2>
          <span className="note">Demand, coverage and where the agent hands off</span>
        </div>
        {volume.data && intents.data && escalations.data && languages.data && kpis.data ? (
          <Operations
            volume={volume.data}
            intents={intents.data}
            escalations={escalations.data}
            languages={languages.data}
            overallContainment={kpis.data.containment_pct}
          />
        ) : (
          <Card><div className="empty">Loading…</div></Card>
        )}
      </section>

      {/* 4 — What you didn't know yesterday. */}
      <section className="section">
        <div className="section-head">
          <h2>Customer intelligence</h2>
          <span className="note">
            What every call tells you beyond whether it was answered
          </span>
        </div>
        {sentiment.data && churn.data && gaps.data && upsell.data ? (
          <Intelligence
            sentiment={sentiment.data}
            churn={churn.data}
            gaps={gaps.data}
            upsell={upsell.data}
          />
        ) : (
          <Card><div className="empty">Loading…</div></Card>
        )}
      </section>
    </div>
    </ChartTokenContext.Provider>
  );
}
