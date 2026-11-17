-- 01_duplicates.sql
-- Flags the later invoice in a same-vendor, same-amount pair
-- where both invoice dates fall within 7 days of each other.
--
-- Same-date tiebreak: flag the invoice with the higher invoice_id
-- (pipeline order). A real system would use the vendor's own reference
-- number or receipt timestamp instead.

SELECT
    b.invoice_id,
    'Duplicate: same vendor and amount as ' || a.invoice_id
        || ' (gap ' ||
        CAST(
            CAST(julianday(b.invoice_date) - julianday(a.invoice_date) AS INTEGER)
        AS TEXT)
        || ' days)' AS reason
FROM invoices a
JOIN invoices b
    ON  a.vendor_id  = b.vendor_id
    AND a.amount_inr = b.amount_inr
    AND (
        (    b.invoice_date >  a.invoice_date
         AND julianday(b.invoice_date) - julianday(a.invoice_date) <= 7
        )
        OR
        (    b.invoice_date = a.invoice_date
         AND a.invoice_id   < b.invoice_id
        )
    )
ORDER BY b.invoice_id
