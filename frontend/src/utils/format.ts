import type { DateRange } from "../types";

// Format backend Decimal strings exactly; no frontend currency conversion.
export const preciseMoney = (value: string | number | null) => {
  if (value === null) return "Historical Toman amount unavailable (legacy)";
  if (typeof value === "number")
    return (
      new Intl.NumberFormat("en-US", { maximumFractionDigits: 2 }).format(
        value,
      ) + " \u062a\u0648\u0645\u0627\u0646"
    );
  const [whole, fraction = ""] = value.split(".");
  const grouped = new Intl.NumberFormat("en-US").format(BigInt(whole));
  const decimals = fraction.replace(/0+$/, "");
  return (
    grouped +
    (decimals ? "." + decimals : "") +
    " \u062a\u0648\u0645\u0627\u0646"
  );
};
export const money = preciseMoney;
export const number = (value: number) =>
  new Intl.NumberFormat("en-US").format(value);
export const shortMoney = (value: number) =>
  new Intl.NumberFormat("en-US", {
    notation: "compact",
    maximumFractionDigits: 1,
  }).format(value) + " \u062a\u0648\u0645\u0627\u0646";
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
