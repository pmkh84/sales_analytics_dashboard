import {
  Area,
  AreaChart,
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  Pie,
  PieChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { ArrowUpRight } from "lucide-react";
import type { Category, Product, TrendPoint } from "../types";
import { money, shortDate, shortMoney } from "../utils/format";
import { EmptyState } from "./States";

const COLORS = ["#246957", "#7fae99", "#b7cbb7", "#e4bc79", "#9aaac0"];
export function RevenueChart({
  data,
  total,
}: {
  data: TrendPoint[];
  total: string;
}) {
  return (
    <section className="card chart-card">
      <div className="card-heading">
        <div>
          <h2>Revenue overview</h2>
          <p>A closer look at your sales performance</p>
        </div>
        <span className="legend-dot">Revenue</span>
      </div>
      <div className="chart-summary">
        {money(total)}
        <span>
          Total revenue this period <ArrowUpRight size={14} />
        </span>
      </div>
      {data.every((point) => point.orders === 0) ? (
        <EmptyState />
      ) : (
        <div
          className="revenue-chart"
          role="img"
          aria-label="Daily revenue area chart"
        >
          <ResponsiveContainer width="100%" height="100%">
            <AreaChart
              data={data}
              margin={{ top: 12, right: 12, left: 0, bottom: 0 }}
            >
              <defs>
                <linearGradient id="revenue-fill" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="0%" stopColor="#6da58d" stopOpacity={0.28} />
                  <stop offset="100%" stopColor="#6da58d" stopOpacity={0.01} />
                </linearGradient>
              </defs>
              <CartesianGrid
                vertical={false}
                stroke="#eef0ed"
                strokeDasharray="4 4"
              />
              <XAxis
                dataKey="date"
                tickFormatter={shortDate}
                minTickGap={38}
                axisLine={false}
                tickLine={false}
                tick={{ fill: "#8a928e", fontSize: 11 }}
                dy={10}
              />
              <YAxis
                tickFormatter={shortMoney}
                axisLine={false}
                tickLine={false}
                tick={{ fill: "#8a928e", fontSize: 11 }}
                width={85}
              />
              <Tooltip
                formatter={(value) => [money(Number(value)), "Revenue"]}
                labelFormatter={(value) => shortDate(String(value))}
                contentStyle={{ borderRadius: 12, borderColor: "#e6eae5" }}
              />
              <Area
                type="monotone"
                dataKey="revenue"
                stroke="#347b62"
                strokeWidth={2.5}
                fill="url(#revenue-fill)"
                isAnimationActive={false}
              />
            </AreaChart>
          </ResponsiveContainer>
        </div>
      )}
    </section>
  );
}
export function CategoryChart({ data }: { data: Category[] }) {
  const total = data.reduce((sum, category) => sum + category.revenue, 0);
  return (
    <section className="card chart-card">
      <div className="card-heading">
        <div>
          <h2>Sales by category</h2>
          <p>Where your revenue comes from</p>
        </div>
      </div>
      {!data.length ? (
        <EmptyState />
      ) : (
        <>
          <div
            className="donut-wrap"
            role="img"
            aria-label="Revenue share by product category"
          >
            <ResponsiveContainer width="100%" height="100%">
              <PieChart>
                <Pie
                  data={data}
                  dataKey="revenue"
                  nameKey="category"
                  innerRadius={68}
                  outerRadius={88}
                  paddingAngle={4}
                  cornerRadius={4}
                  stroke="none"
                  isAnimationActive={false}
                >
                  {data.map((item, index) => (
                    <Cell
                      key={item.category}
                      fill={COLORS[index % COLORS.length]}
                    />
                  ))}
                </Pie>
                <Tooltip formatter={(value) => money(Number(value))} />
              </PieChart>
            </ResponsiveContainer>
            <div className="donut-center">
              <strong>{data.length}</strong>
              <span>Categories</span>
            </div>
          </div>
          <div className="category-legend">
            {data.map((item, index) => (
              <div key={item.category}>
                <span
                  className="category-dot"
                  style={{ background: COLORS[index % COLORS.length] }}
                />
                <span>{item.category}</span>
                <strong>
                  {total ? ((item.revenue / total) * 100).toFixed(1) : 0}%
                </strong>
              </div>
            ))}
          </div>
        </>
      )}
    </section>
  );
}
export function ProductsChart({ data }: { data: Product[] }) {
  return (
    <section className="card chart-card products-card">
      <div className="card-heading">
        <div>
          <h2>Top products</h2>
          <p>Your best performers, ranked by revenue</p>
        </div>
        <span className="subtle-badge">TOP 5</span>
      </div>
      {!data.length ? (
        <EmptyState />
      ) : (
        <div
          className="products-chart"
          role="img"
          aria-label="Top five products by revenue"
        >
          <ResponsiveContainer width="100%" height="100%">
            <BarChart
              data={data}
              layout="vertical"
              margin={{ left: 0, right: 18, top: 10, bottom: 0 }}
            >
              <CartesianGrid
                horizontal={false}
                stroke="#eef0ed"
                strokeDasharray="4 4"
              />
              <XAxis
                type="number"
                tickFormatter={shortMoney}
                axisLine={false}
                tickLine={false}
                tick={{ fontSize: 10, fill: "#8a928e" }}
              />
              <YAxis
                type="category"
                dataKey="name"
                width={125}
                axisLine={false}
                tickLine={false}
                tick={{ fontSize: 11, fill: "#626d67" }}
              />
              <Tooltip
                formatter={(value) => money(Number(value))}
                cursor={{ fill: "#f5f7f4" }}
              />
              <Bar
                dataKey="revenue"
                name="Revenue"
                fill="#74a58d"
                radius={[0, 4, 4, 0]}
                barSize={17}
                isAnimationActive={false}
              />
            </BarChart>
          </ResponsiveContainer>
        </div>
      )}
    </section>
  );
}
