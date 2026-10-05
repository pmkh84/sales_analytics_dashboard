import { AIPanel } from "../components/AIPanel";
import {
  CategoryChart,
  ProductsChart,
  RevenueChart,
} from "../components/Charts";
import { KpiCards } from "../components/KpiCards";
import { SalesTable } from "../components/SalesTable";
import type { DashboardData, DateRange, Page } from "../types";

export function Dashboard({
  data,
  range,
  revision,
  page,
  setPage,
}: {
  data: DashboardData;
  range: DateRange;
  revision: number;
  page: Page;
  setPage: (page: Page) => void;
}) {
  if (page === "Sales") return <SalesTable range={range} revision={revision} />;
  if (page === "AI Insights")
    return (
      <>
        <div className="analysis-banner">
          <span className="status-dot" />
          Your analyst sees the same selected period as your dashboard. No
          customer details are sent to AI.
        </div>
        <AIPanel range={range} expanded />
      </>
    );
  return (
    <>
      <KpiCards summary={data.summary} />
      <div className="chart-grid">
        <RevenueChart data={data.trend} total={data.summary.total_revenue} />
        <CategoryChart data={data.categories} />
      </div>
      {page === "Dashboard" ? (
        <>
          <div className="bottom-grid">
            <ProductsChart data={data.products} />
            <AIPanel range={range} />
          </div>
          <SalesTable
            range={range}
            revision={revision}
            compact
            onViewAll={() => setPage("Sales")}
          />
        </>
      ) : (
        <>
          <ProductsChart data={data.products} />
          <div className="analysis-banner">
            Revenue is gross sales after recorded discounts. Each sale is one
            order. Customer count represents unique buyers in this period.
          </div>
        </>
      )}
    </>
  );
}
