import {
  ArrowDownRight,
  ArrowUpRight,
  Banknote,
  ShoppingBag,
  Users,
  Wallet,
} from "lucide-react";
import type { Summary } from "../types";
import { money, number, preciseMoney } from "../utils/format";

export function KpiCards({ summary }: { summary: Summary }) {
  const cards = [
    {
      title: "Total revenue",
      value:
        summary.legacy_orders > 0 && summary.priced_orders === 0
          ? "Unavailable"
          : money(summary.total_revenue),
      icon: Banknote,
      note: "vs. previous period",
      growth: summary.revenue_growth,
    },
    {
      title: "Total orders",
      value: number(summary.total_orders),
      icon: ShoppingBag,
      note: "Orders in selected period",
    },
    {
      title: "Customers",
      value: number(summary.total_customers),
      icon: Users,
      note: "Unique purchasing customers",
    },
    {
      title: "Average order value",
      value:
        summary.legacy_orders > 0 && summary.priced_orders === 0
          ? "Unavailable"
          : preciseMoney(summary.average_order_value),
      icon: Wallet,
      note: "Revenue per priced order",
    },
  ];
  return (
    <div className="kpi-grid">
      {cards.map(({ title, value, icon: Icon, note, growth }, index) => (
        <section
          className={"card kpi " + (index === 0 ? "featured" : "")}
          key={title}
        >
          <div className="kpi-label">
            {title}
            <span className="kpi-icon">
              <Icon size={17} />
            </span>
          </div>
          <div className="kpi-value">{value}</div>
          <div className="kpi-note">
            {growth !== undefined &&
              (growth === null ? (
                <span>
                  {summary.legacy_orders || summary.previous_legacy_orders
                    ? "Comparison unavailable (legacy sales)"
                    : "No prior revenue"}
                </span>
              ) : (
                <span className={"growth " + (growth < 0 ? "negative" : "")}>
                  {growth < 0 ? (
                    <ArrowDownRight size={13} />
                  ) : (
                    <ArrowUpRight size={13} />
                  )}
                  {Math.abs(growth).toFixed(1)}%
                </span>
              ))}
            <span>{growth === null ? "" : note}</span>
          </div>
        </section>
      ))}
    </div>
  );
}
