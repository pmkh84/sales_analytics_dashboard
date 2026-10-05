import { useEffect, useState } from "react";
import { errorMessage, getDashboard } from "../services/api";
import type { DashboardData, DateRange } from "../types";

export function useDashboard(range: DateRange, revision: number) {
  const [data, setData] = useState<DashboardData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  useEffect(() => {
    const controller = new AbortController();
    setLoading(true);
    setError("");
    getDashboard(range, controller.signal)
      .then(setData)
      .catch((error: unknown) => {
        if (!controller.signal.aborted) setError(errorMessage(error));
      })
      .finally(() => {
        if (!controller.signal.aborted) setLoading(false);
      });
    return () => controller.abort();
  }, [range, revision]);
  return { data, loading, error };
}
