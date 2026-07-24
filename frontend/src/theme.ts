import { createContext, useCallback, useContext, useEffect, useState } from "react";

export type Theme = "light" | "dark";

const STORAGE_KEY = "callagent.theme";

/**
 * Theme state. Defaults to the OS preference and persists an explicit choice.
 *
 * Demo note: set the theme once with the toggle before presenting — the choice
 * is remembered, so a projector-friendly dark won't be undone by the laptop's
 * OS setting mid-demo.
 */
export function useTheme(): [Theme, () => void] {
  const [theme, setTheme] = useState<Theme>(() => resolveInitialTheme());

  useEffect(() => {
    document.documentElement.setAttribute("data-theme", theme);
    try {
      localStorage.setItem(STORAGE_KEY, theme);
    } catch {
      /* private browsing — the attribute above still applies for this session */
    }
  }, [theme]);

  const toggle = useCallback(
    () => setTheme((t) => (t === "dark" ? "light" : "dark")),
    [],
  );

  return [theme, toggle];
}

export function resolveInitialTheme(): Theme {
  try {
    const saved = localStorage.getItem(STORAGE_KEY);
    if (saved === "light" || saved === "dark") return saved;
  } catch {
    /* ignore */
  }
  return window.matchMedia?.("(prefers-color-scheme: light)").matches ? "light" : "dark";
}

/* ------------------------------------------------------------- chart ink -- */

/**
 * Recharts writes colours as SVG *presentation attributes*, where `var(--x)`
 * support is inconsistent across engines — a token that renders correctly in one
 * theme can resolve to nothing in another and paint black. So we read the
 * computed values once per theme and hand Recharts real hex.
 *
 * CSS-styled elements (everything outside the charts) keep using the tokens
 * directly; only the SVG layer needs this.
 */
export const CHART_TOKENS = [
  "--series-1", "--series-2", "--series-3", "--series-4",
  "--serious", "--good", "--critical",
  "--axis", "--grid", "--text-muted", "--hover-wash", "--surface-1",
] as const;

export type ChartTokens = Record<(typeof CHART_TOKENS)[number], string>;

const FALLBACK: ChartTokens = {
  "--series-1": "#3987e5", "--series-2": "#d95926",
  "--series-3": "#199e70", "--series-4": "#c98500",
  "--serious": "#ec835a", "--good": "#0ca30c", "--critical": "#d03b3b",
  "--axis": "#34373d", "--grid": "#24262b", "--text-muted": "#8a8d96",
  "--hover-wash": "rgba(255,255,255,0.04)", "--surface-1": "#16171a",
};

export function useChartTokens(theme: Theme): ChartTokens {
  const [tokens, setTokens] = useState<ChartTokens>(FALLBACK);

  useEffect(() => {
    // Next frame: the data-theme attribute write above must land first.
    const id = requestAnimationFrame(() => {
      const cs = getComputedStyle(document.documentElement);
      const next = {} as ChartTokens;
      for (const t of CHART_TOKENS) {
        next[t] = cs.getPropertyValue(t).trim() || FALLBACK[t];
      }
      setTokens(next);
    });
    return () => cancelAnimationFrame(id);
  }, [theme]);

  return tokens;
}

export const ChartTokenContext = createContext<ChartTokens>(FALLBACK);
export const useTokens = () => useContext(ChartTokenContext);
