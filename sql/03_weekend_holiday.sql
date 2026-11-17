-- 03_weekend_holiday.sql
-- Flags invoices whose payment_date falls on a Saturday, Sunday,
-- or a date in the holidays table.

SELECT
    i.invoice_id,
    'Weekend/holiday payment: payment_date ' || i.payment_date
        || ' is a '
        || CASE
               WHEN CAST(strftime('%w', i.payment_date) AS INTEGER) = 0 THEN 'Sunday'
               WHEN CAST(strftime('%w', i.payment_date) AS INTEGER) = 6 THEN 'Saturday'
               ELSE 'public holiday (' || h.holiday_name || ')'
           END AS reason
FROM invoices i
LEFT JOIN holidays h
    ON h.date = i.payment_date
WHERE
    CAST(strftime('%w', i.payment_date) AS INTEGER) = 6
    OR
    CAST(strftime('%w', i.payment_date) AS INTEGER) = 0
    OR
    h.date IS NOT NULL
ORDER BY i.invoice_id
