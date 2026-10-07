import axios from "axios";
import type {
  Category,
  CreatedSale,
  CreateSaleRequest,
  CustomerOption,
  DashboardData,
  DateRange,
  ExchangeRate,
  Insight,
  Product,
  ProductOption,
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
    if (error.response?.status === 422)
      return "Check the selected customer, product, and positive whole-number quantity.";
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
export async function getCustomers(signal: AbortSignal) {
  return (await api.get<CustomerOption[]>("/api/customers", { signal })).data;
}

export async function getExchangeRate(signal: AbortSignal) {
  return (
    await api.get<ExchangeRate>("/api/exchange-rate", {
      signal,
      timeout: 10000,
    })
  ).data;
}
export async function getProducts(signal: AbortSignal) {
  return (await api.get<ProductOption[]>("/api/products", { signal })).data;
}
export async function createSale(request: CreateSaleRequest) {
  return (await api.post<CreatedSale>("/api/sales", request)).data;
}
export async function deleteSale(id: number): Promise<void> {
  await api.delete(`/api/sales/${id}`);
}
export async function updateSale(id: number, request: CreateSaleRequest) {
  return (await api.patch<CreatedSale>(`/api/sales/${id}`, request)).data;
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
