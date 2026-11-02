import { useEffect, useState } from "react";
import { CalendarRange, Database, Moon, Sun } from "lucide-react";

import { AnalyticsBento } from "@/components/ui/analytics-bento";
import {
  dashboardData,
  dashboardMeta,
  type DashboardData,
} from "@/data/dashboard-data";

function useFonts() {
  useEffect(() => {
    const id = "geist-fonts";
    if (document.getElementById(id)) return;
    const link = document.createElement("link");
    link.id = id;
    link.rel = "stylesheet";
    link.href =
      "https://fonts.googleapis.com/css2?family=Geist:wght@400;500;600&family=Geist+Mono:wght@400;500&display=swap";
    document.head.appendChild(link);
  }, []);
}

function formatDate(value: string) {
  return new Date(`${value}T00:00:00`).toLocaleDateString("en-US", {
    month: "short",
    day: "numeric",
    year: "numeric",
  });
}

function App() {
  useFonts();
  const [dark, setDark] = useState(false);
  const data =
    (window as Window & { __SALES_DATA__?: DashboardData }).__SALES_DATA__ ??
    dashboardData;

  useEffect(() => {
    document.documentElement.classList.toggle("dark", dark);
  }, [dark]);

  return (
    <div
      className="min-h-screen w-full bg-background px-4 py-8 text-foreground sm:px-6 sm:py-10"
      style={{
        backgroundImage:
          "radial-gradient(circle, color-mix(in oklab, var(--color-foreground) 7%, transparent) 0 1px, transparent 1.4px)",
        backgroundSize: "20px 13px",
        backgroundPosition: "-6px -1px",
      }}
    >
      <div className="mx-auto max-w-[1240px]">
        <header className="mb-6 flex flex-col gap-4 sm:mb-8 sm:flex-row sm:items-end sm:justify-between">
          <div>
            <div className="inline-flex items-center gap-2 rounded-full border border-border bg-card px-3 py-1 text-[11px] font-medium uppercase tracking-[0.14em] text-muted-foreground shadow-sm">
              <Database className="size-3.5" />
              {dashboardMeta.source} · data snapshot
            </div>
            <h1 className="mt-3 text-3xl font-semibold tracking-[-0.04em] sm:text-4xl">
              Sales overview
            </h1>
            <p className="mt-1.5 max-w-2xl text-sm leading-6 text-muted-foreground">
              Revenue, store activity, product groups and seasonality for the
              printer business. Gross sales, before returns and approval/status
              filters.
            </p>
          </div>
          <div className="flex items-center gap-2">
            <div className="hidden items-center gap-2 rounded-full border border-border bg-card px-3 py-2 text-xs text-muted-foreground shadow-sm sm:flex">
              <CalendarRange className="size-3.5" />
              <span>
                {formatDate(dashboardMeta.dataRange.from)} –{" "}
                {formatDate(dashboardMeta.dataRange.to)}
              </span>
            </div>
            <button
              type="button"
              onClick={() => setDark((value) => !value)}
              aria-label={dark ? "Use light theme" : "Use dark theme"}
              className="inline-flex size-9 items-center justify-center rounded-full border border-border bg-card text-muted-foreground shadow-sm outline-none transition-colors hover:bg-muted hover:text-foreground focus-visible:ring-2 focus-visible:ring-ring"
            >
              {dark ? <Sun className="size-4" /> : <Moon className="size-4" />}
            </button>
          </div>
        </header>

        <AnalyticsBento
          currency={dashboardMeta.currency}
          revenue={data.revenue}
          sessions={data.sessions}
          categories={data.categories}
          seasonality={data.seasonality}
        />

        <footer className="mt-6 flex flex-col gap-2 border-t border-border pt-4 text-xs text-muted-foreground sm:flex-row sm:items-center sm:justify-between">
          <span>
            Source: {dashboardMeta.source} ·{" "}
            {dashboardMeta.totalOrders.toLocaleString("en-US")} orders ·{" "}
            {dashboardMeta.totalRows.toLocaleString("en-US")} line items
          </span>
          <span>
            Snapshot generated{" "}
            {new Date(dashboardMeta.generatedAt).toLocaleString("en-US", {
              dateStyle: "medium",
              timeStyle: "short",
            })}
          </span>
        </footer>
      </div>
    </div>
  );
}

export default App;
