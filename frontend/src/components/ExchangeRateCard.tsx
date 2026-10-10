import { useExchangeRate } from "../hooks/useExchangeRate";

const rateFormat = new Intl.NumberFormat("en-US", {
  maximumFractionDigits: 20,
});
const updateFormat = new Intl.DateTimeFormat("en-GB", {
  hour: "2-digit",
  minute: "2-digit",
  timeZone: "Asia/Tehran",
});

export function ExchangeRateCard({ revision }: { revision: number }) {
  const { data, loading, unavailable } = useExchangeRate(revision);
  return (
    <section
      className="card exchange-rate-card"
      aria-label="USD to Toman exchange rate"
      aria-live="polite"
    >
      <span className="exchange-rate-label">USD / Toman</span>
      {data ? (
        <>
          <strong className="exchange-rate-value">
            {rateFormat.format(Number(data.rate))}{" "}
            <span lang="fa" dir="rtl">
              تومان
            </span>
          </strong>
          <span
            className="exchange-rate-meta"
            title={`${data.source} · Tehran market buy rate`}
          >
            {data.stale ? (
              <span className="exchange-rate-stale">Last known rate · </span>
            ) : (
              "Updated: "
            )}
            <time
              dateTime={data.updated_at}
              title={new Date(data.updated_at).toLocaleString("en-GB", {
                timeZone: "Asia/Tehran",
              })}
            >
              {updateFormat.format(new Date(data.updated_at))}
            </time>{" "}
            Tehran
          </span>
        </>
      ) : loading ? (
        <span className="exchange-rate-meta" role="status">
          Loading exchange rate…
        </span>
      ) : unavailable ? (
        <span className="exchange-rate-meta">Exchange rate unavailable</span>
      ) : null}
    </section>
  );
}
