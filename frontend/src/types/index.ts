export type Page = "Dashboard" | "Analytics" | "Sales" | "AI Insights";
export interface DateRange {
  start_date: string;
  end_date: string;
}
export interface Summary {
  total_revenue: string;
  total_orders: number;
  total_customers: number;
  average_order_value: string;
  revenue_growth: number | null;
  previous_revenue: string;
  currency: "IRT";
  priced_orders: number;
  legacy_orders: number;
  previous_legacy_orders: number;
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
  customer_id: number;
  product_id: number;
  customer_name: string;
  product_name: string;
  category: string;
  quantity: number;
  total_amount: string; // USD compatibility field
  exchange_rate_toman: string | null;
  total_amount_toman: string | null;
  created_at: string;
}
export interface SalesPage {
  items: Sale[];
  total: number;
  limit: number;
  offset: number;
}
export interface CustomerOption {
  id: number;
  name: string;
}
export interface ProductOption extends CustomerOption {
  price: string; // USD compatibility field
  price_usd: string;
  price_toman: string | null;
  exchange_rate_stale: boolean | null;
}
export interface CreateSaleRequest {
  customer_id: number;
  product_id: number;
  quantity: number;
}
export interface CreatedSale extends CreateSaleRequest {
  id: number;
  total_amount: string; // USD compatibility field
  exchange_rate_toman: string | null;
  total_amount_toman: string | null;
  created_at: string;
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

export interface ExchangeRate {
  base: "USD";
  quote: "IRT";
  rate: string;
  updated_at: string;
  source: "Navasan";
  stale: boolean;
}
