import { useMemo, useState } from "react";
import { CalendarDays, RefreshCw } from "lucide-react";
import { Layout } from "./components/Layout";
import { DashboardSkeleton, ErrorState } from "./components/States";
import { useDashboard } from "./hooks/useDashboard";
import { Dashboard } from "./pages/Dashboard";
import { getRange, rangeLabel } from "./utils/format";
import type { Page } from "./types";

const descriptions: Record<Page, string> = {
  Dashboard: "Welcome back. Here's how your business is doing.",
  Analytics: "Go beyond the numbers. Find what moves your business.",
  Sales: "Every transaction, all in one place.",
  "AI Insights": "Make your next decision an informed one.",
};
export default function App() {
  const [page, setPage] = useState<Page>("Dashboard");
  const [days, setDays] = useState(30);
  const [revision, setRevision] = useState(0);
  const range = useMemo(() => getRange(days), [days, revision]);
  const { data, loading, error } = useDashboard(range, revision);
  return (
    <Layout page={page} setPage={setPage}>
      <div className="page-heading">
        <div>
          <div className="eyebrow">YOUR BUSINESS, AT A GLANCE</div>
          <h1>{page === "Dashboard" ? "Sales overview" : page}</h1>
          <p>{descriptions[page]}</p>
        </div>
        <div className="page-actions">
          <label className="date-select">
            <CalendarDays size={16} />
            <span className="sr-only">Date range</span>
            <select
              value={days}
              onChange={(event) => setDays(Number(event.target.value))}
            >
              <option value={30}>Last 30 days</option>
              <option value={90}>Last 90 days</option>
              <option value={210}>Last 7 months</option>
            </select>
          </label>
          <button
            className="icon-button refresh"
            aria-label="Refresh dashboard"
            disabled={loading}
            onClick={() => setRevision((value) => value + 1)}
          >
            <RefreshCw size={17} className={loading ? "animate-spin" : ""} />
          </button>
        </div>
      </div>
      <div className="period-line">
        <span>
          <span className="status-dot" />
          {rangeLabel(range)}
        </span>
        <span>Compared with the previous {days} days</span>
      </div>
      {loading ? (
        <DashboardSkeleton />
      ) : error ? (
        <ErrorState
          message={error}
          retry={() => setRevision((value) => value + 1)}
        />
      ) : (
        data && (
          <Dashboard
            key={range.start_date + range.end_date + revision + page}
            data={data}
            range={range}
            revision={revision}
            page={page}
            setPage={setPage}
          />
        )
      )}
    </Layout>
  );
}
