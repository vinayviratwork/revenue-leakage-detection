-- 02_split_invoices.sql
-- Flags clusters where the same vendor + approver submit multiple invoices
-- each in the 80–98% band of the approval limit, within a 3-day window,
-- and the cluster total exceeds the limit.
-- Approval limit is passed as a named parameter: :approval_limit

WITH clusters AS (
    SELECT
        a.vendor_id,
        a.approver_id,
        a.invoice_id  AS inv_a,
        b.invoice_id  AS inv_b,
        a.amount_inr  AS amt_a,
        b.amount_inr  AS amt_b,
        a.invoice_date AS date_a,
        b.invoice_date AS date_b
    FROM invoices a
    JOIN invoices b
        ON  a.vendor_id   = b.vendor_id
        AND a.approver_id = b.approver_id
        AND a.invoice_id  < b.invoice_id
        AND a.amount_inr  >= :approval_limit * 0.80
        AND a.amount_inr  <  :approval_limit * 1.00
        AND b.amount_inr  >= :approval_limit * 0.80
        AND b.amount_inr  <  :approval_limit * 1.00
        AND ABS(julianday(b.invoice_date) - julianday(a.invoice_date)) <= 3
    WHERE (a.amount_inr + b.amount_inr) > :approval_limit
),
flagged_ids AS (
    SELECT inv_a AS invoice_id FROM clusters
    UNION
    SELECT inv_b AS invoice_id FROM clusters
)
SELECT
    i.invoice_id,
    'Split invoice: vendor ' || i.vendor_id
        || ', approver ' || i.approver_id
        || ', amount ' || CAST(CAST(i.amount_inr AS INTEGER) AS TEXT)
        || ' (near approval limit)' AS reason
FROM invoices i
JOIN flagged_ids f ON i.invoice_id = f.invoice_id
ORDER BY i.invoice_id
