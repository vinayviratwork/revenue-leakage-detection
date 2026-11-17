-- 04_round_figure.sql
-- Flags invoices with an exact multiple-of-10,000 amount (>= Rs 20,000)
-- for vendors whose overall round-figure rate is below 15%.
-- Vendors like retainer/rent vendors naturally issue round amounts and
-- are excluded by the round_rate filter.

WITH vendor_stats AS (
    SELECT
        vendor_id,
        COUNT(*)  AS total_invoices,
        SUM(
            CASE
                WHEN amount_inr >= 20000
                     AND (CAST(amount_inr AS INTEGER) % 10000) = 0
                     AND amount_inr = CAST(amount_inr AS INTEGER)
                THEN 1 ELSE 0
            END
        ) AS round_count,
        CAST(
            SUM(
                CASE
                    WHEN amount_inr >= 20000
                         AND (CAST(amount_inr AS INTEGER) % 10000) = 0
                         AND amount_inr = CAST(amount_inr AS INTEGER)
                    THEN 1 ELSE 0
                END
            ) AS REAL
        ) / COUNT(*) AS round_rate
    FROM invoices
    GROUP BY vendor_id
)
SELECT
    i.invoice_id,
    'Round figure: amount Rs ' || CAST(CAST(i.amount_inr AS INTEGER) AS TEXT)
        || ' for vendor ' || i.vendor_id
        || ' (vendor round rate '
        || CAST(CAST(vs.round_rate * 100 AS INTEGER) AS TEXT)
        || '%, below 15% threshold)' AS reason
FROM invoices i
JOIN vendor_stats vs ON i.vendor_id = vs.vendor_id
WHERE
    i.amount_inr >= 20000
    AND (CAST(i.amount_inr AS INTEGER) % 10000) = 0
    AND i.amount_inr = CAST(i.amount_inr AS INTEGER)
    AND vs.round_rate < 0.15
ORDER BY i.invoice_id
