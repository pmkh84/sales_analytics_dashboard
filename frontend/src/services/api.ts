import axios from "axios";
import type {
  Category,
  DashboardData,
  DateRange,
  Insight,
  Product,
  SalesPage,
  Summary,
  TrendPoint,
} from "../types";

export const api = axios.create({
  baseURL: (import.meta.env.VITE_API_URL || "http://localhost:8000").replace(
    /\/$/,
    "",
  ),
  timeout: 45000,
});
export function errorMessage(error: unknown): string {
  if (axios.isAxiosError(error)) {
    const detail: unknown = error.response?.data?.detail;
    if (typeof detail === "string") return detail;
    if (error.code === "ECONNABORTED")
      return "The request timed out. Please try again.";
    if (!error.response)
      return "Cannot reach the server. Check that the backend is running and VITE_API_URL is correct.";
    return "We could not load this data. Please try again.";
  }
  return "Something went wrong. Please try again.";
}
export async function getDashboard(
  range: DateRange,
  signal: AbortSignal,
): Promise<DashboardData> {
  const params = { ...range };
  const [summary, trend, categories, products] = await Promise.all([
    api.get<Summary>("/api/dashboard/summary", { params, signal }),
    api.get<TrendPoint[]>("/api/dashboard/revenue-trend", { params, signal }),
    api.get<Category[]>("/api/dashboard/categories", { params, signal }),
    api.get<Product[]>("/api/dashboard/top-products", { params, signal }),
  ]);
  return {
    summary: summary.data,
    trend: trend.data,
    categories: categories.data,
    products: products.data,
  };
}
export async function getSales(
  range: DateRange,
  offset: number,
  signal: AbortSignal,
) {
  return (
    await api.get<SalesPage>("/api/sales/recent", {
      params: { ...range, limit: 8, offset },
      signal,
    })
  ).data;
}
export async function getInsights(range: DateRange) {
  return (
    await api.get<{ insights: Insight[] }>("/api/ai/insights", {
      params: range,
    })
  ).data.insights;
}
export async function askAI(question: string, range: DateRange) {
  return (
    await api.post<{ answer: string }>(
      "/api/ai/ask",
      { question },
      { params: range },
    )
  ).data.answer;
}
