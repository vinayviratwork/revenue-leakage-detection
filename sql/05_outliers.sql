-- 05_outliers.sql
-- Flags invoices where the amount exceeds the vendor's mean + 3 std devs.
-- Only vendors with at least 10 invoices are included (need a stable baseline).
-- SQLite has no STDDEV function so it's computed manually:
--   std = sqrt( avg(x^2) - avg(x)^2 )

WITH vendor_stats AS (
    SELECT
        vendor_id,
        COUNT(*)    AS invoice_count,
        AVG(amount_inr) AS mean_amount,
        SQRT(
            MAX(AVG(amount_inr * amount_inr) - AVG(amount_inr) * AVG(amount_inr), 0)
        ) AS std_amount
    FROM invoices
    GROUP BY vendor_id
    HAVING COUNT(*) >= 10
)
SELECT
    i.invoice_id,
    'Outlier: amount Rs ' || CAST(CAST(i.amount_inr AS INTEGER) AS TEXT)
        || ' vs vendor mean Rs ' || CAST(CAST(vs.mean_amount AS INTEGER) AS TEXT)
        || ' (+'
        || CAST(
               CAST(
                   ROUND((i.amount_inr - vs.mean_amount) / NULLIF(vs.std_amount, 0), 1)
               AS REAL)
           AS TEXT)
        || ' std devs)' AS reason
FROM invoices i
JOIN vendor_stats vs ON i.vendor_id = vs.vendor_id
WHERE
    vs.std_amount > 0
    AND i.amount_inr > vs.mean_amount + 3.0 * vs.std_amount
ORDER BY i.invoice_id
