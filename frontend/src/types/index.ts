export type Page = "Dashboard" | "Analytics" | "Sales" | "AI Insights";
export interface DateRange {
  start_date: string;
  end_date: string;
}
export interface Summary {
  total_revenue: number;
  total_orders: number;
  total_customers: number;
  average_order_value: number;
  revenue_growth: number | null;
  previous_revenue: number;
  start_date: string;
  end_date: string;
}
export interface TrendPoint {
  date: string;
  revenue: number;
  orders: number;
}
export interface Category {
  category: string;
  revenue: number;
  orders: number;
  units: number;
}
export interface Product {
  id: number;
  name: string;
  category: string;
  revenue: number;
  units: number;
}
export interface Sale {
  id: number;
  customer_name: string;
  product_name: string;
  category: string;
  quantity: number;
  total_amount: number;
  created_at: string;
}
export interface SalesPage {
  items: Sale[];
  total: number;
  limit: number;
  offset: number;
}
export interface Insight {
  title: string;
  detail: string;
}
export interface DashboardData {
  summary: Summary;
  trend: TrendPoint[];
  categories: Category[];
  products: Product[];
}
