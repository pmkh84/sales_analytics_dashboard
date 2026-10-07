import { useEffect, useState } from "react";
import { getExchangeRate } from "../services/api";
import type { ExchangeRate } from "../types";

export function useExchangeRate(revision: number) {
  const [data, setData] = useState<ExchangeRate | null>(null);
  const [loading, setLoading] = useState(true);
  const [unavailable, setUnavailable] = useState(false);

  useEffect(() => {
    let controller: AbortController;
    const load = () => {
      controller?.abort();
      const current = new AbortController();
      controller = current;
      setLoading(true);
      getExchangeRate(current.signal)
        .then((rate) => {
          if (current.signal.aborted) return;
          setData(rate);
          setUnavailable(false);
        })
        .catch(() => {
          if (current.signal.aborted) return;
          setData(null);
          setUnavailable(true);
        })
        .finally(() => {
          if (!current.signal.aborted) setLoading(false);
        });
    };
    load();
    const timer = window.setInterval(() => {
      if (!document.hidden) load();
    }, 120000);
    return () => {
      window.clearInterval(timer);
      controller.abort();
    };
  }, [revision]);

  return { data, loading, unavailable };
}
