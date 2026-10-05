import { AlertCircle, Inbox } from "lucide-react";

export function ErrorState({
  message,
  retry,
}: {
  message: string;
  retry?: () => void;
}) {
  return (
    <div role="alert" className="error-state">
      <AlertCircle size={20} />
      <div>
        <strong>Something needs attention</strong>
        <p>{message}</p>
      </div>
      {retry && (
        <button className="button secondary" onClick={retry}>
          Try again
        </button>
      )}
    </div>
  );
}
export function EmptyState({
  message = "No sales in this period. Try a wider date range.",
}: {
  message?: string;
}) {
  return (
    <div className="empty-state">
      <Inbox size={28} />
      <p>{message}</p>
    </div>
  );
}
export function DashboardSkeleton() {
  return (
    <div aria-label="Loading dashboard" role="status">
      <span className="sr-only">Loading dashboard…</span>
      <div className="kpi-grid">
        {[1, 2, 3, 4].map((i) => (
          <div key={i} className="card skeleton h-32" />
        ))}
      </div>
      <div className="chart-grid mt-6">
        <div className="card skeleton h-80" />
        <div className="card skeleton h-80" />
      </div>
    </div>
  );
}
