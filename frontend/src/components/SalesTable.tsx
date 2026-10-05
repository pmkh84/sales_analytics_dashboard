import { useEffect, useState } from "react";
import { ArrowRight, ChevronLeft, ChevronRight } from "lucide-react";
import type { DateRange, SalesPage } from "../types";
import { errorMessage, getSales } from "../services/api";
import { number, preciseMoney, shortDate } from "../utils/format";
import { EmptyState, ErrorState } from "./States";

export function SalesTable({
  range,
  revision,
  compact = false,
  onViewAll,
}: {
  range: DateRange;
  revision: number;
  compact?: boolean;
  onViewAll?: () => void;
}) {
  const [offset, setOffset] = useState(0);
  const [data, setData] = useState<SalesPage | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [retry, setRetry] = useState(0);
  useEffect(() => {
    const controller = new AbortController();
    setLoading(true);
    setError("");
    getSales(range, offset, controller.signal)
      .then(setData)
      .catch((error: unknown) => {
        if (!controller.signal.aborted) setError(errorMessage(error));
      })
      .finally(() => {
        if (!controller.signal.aborted) setLoading(false);
      });
    return () => controller.abort();
  }, [range, revision, offset, retry]);
  return (
    <section className="card sales-card">
      <div className="card-heading">
        <div>
          <h2>{compact ? "Recent sales" : "Sales transactions"}</h2>
          <p>Your latest customer activity</p>
        </div>
        {compact && (
          <button className="text-button" onClick={onViewAll}>
            View all sales <ArrowRight size={15} />
          </button>
        )}
      </div>
      {error ? (
        <ErrorState
          message={error}
          retry={() => setRetry((value) => value + 1)}
        />
      ) : loading ? (
        <div role="status" className="table-loading">
          <span className="sr-only">Loading sales…</span>
          {[1, 2, 3, 4].map((i) => (
            <div key={i} className="skeleton h-10 mb-3" />
          ))}
        </div>
      ) : !data?.items.length ? (
        <EmptyState />
      ) : (
        <>
          <div className="table-scroll">
            <table>
              <thead>
                <tr>
                  <th>Order</th>
                  <th>Customer</th>
                  <th>Product</th>
                  <th>Date (UTC)</th>
                  <th>Qty</th>
                  <th className="text-right">Amount</th>
                </tr>
              </thead>
              <tbody>
                {data.items.slice(0, compact ? 5 : 8).map((sale) => (
                  <tr key={sale.id}>
                    <td className="order-id">
                      #{String(sale.id).padStart(4, "0")}
                    </td>
                    <td>
                      <div className="customer-cell">
                        <span className="customer-avatar">
                          {sale.customer_name
                            .split(" ")
                            .map((part) => part[0])
                            .slice(0, 2)
                            .join("")}
                        </span>
                        {sale.customer_name}
                      </div>
                    </td>
                    <td>
                      <strong>{sale.product_name}</strong>
                      <small>{sale.category}</small>
                    </td>
                    <td>{shortDate(sale.created_at)}</td>
                    <td>{sale.quantity}</td>
                    <td className="amount">
                      {preciseMoney(sale.total_amount)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {!compact && (
            <div className="pagination">
              <span>
                Showing {offset + 1}–{Math.min(offset + data.limit, data.total)}{" "}
                of {number(data.total)} orders
              </span>
              <div>
                <button
                  aria-label="Previous page"
                  className="icon-button"
                  disabled={offset === 0}
                  onClick={() => setOffset((value) => Math.max(0, value - 8))}
                >
                  <ChevronLeft size={18} />
                </button>
                <button
                  aria-label="Next page"
                  className="icon-button"
                  disabled={offset + data.limit >= data.total}
                  onClick={() => setOffset((value) => value + 8)}
                >
                  <ChevronRight size={18} />
                </button>
              </div>
            </div>
          )}
        </>
      )}
    </section>
  );
}
