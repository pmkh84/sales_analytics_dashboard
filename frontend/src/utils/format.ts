import type { DateRange } from "../types";

export const money = (value: number) =>
  new Intl.NumberFormat("en-US", {
    style: "currency",
    currency: "USD",
    maximumFractionDigits: 0,
  }).format(value);
export const preciseMoney = (value: number) =>
  new Intl.NumberFormat("en-US", {
    style: "currency",
    currency: "USD",
  }).format(value);
export const number = (value: number) =>
  new Intl.NumberFormat("en-US").format(value);
export const shortMoney = (value: number) =>
  "$" +
  new Intl.NumberFormat("en-US", {
    notation: "compact",
    maximumFractionDigits: 1,
  }).format(value);
export const shortDate = (value: string) =>
  new Date(
    value.length === 10 ? value + "T00:00:00Z" : value,
  ).toLocaleDateString("en-US", {
    month: "short",
    day: "numeric",
    timeZone: "UTC",
  });
export function getRange(days: number): DateRange {
  const end = new Date();
  const start = new Date(end);
  start.setUTCDate(end.getUTCDate() - days + 1);
  return {
    start_date: start.toISOString().slice(0, 10),
    end_date: end.toISOString().slice(0, 10),
  };
}
export function rangeLabel(range: DateRange) {
  return (
    shortDate(range.start_date) +
    " – " +
    shortDate(range.end_date) +
    ", " +
    range.end_date.slice(0, 4)
  );
}
