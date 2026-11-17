"""
export_powerbi.py
Exports a star-schema set of CSVs for Power BI Desktop.

Tables:
  fact_invoices.csv  -- one row per invoice with flags and risk columns
  dim_vendor.csv     -- vendor dimension
  dim_date.csv       -- date dimension (Indian FY, quarter, is_weekend)
  rule_summary.csv   -- per-rule precision/recall/F1

Run from project root:
  python src/export_powerbi.py
"""

import pandas as pd
from pathlib import Path

ROOT        = Path(__file__).parent.parent
SCORED_CSV  = ROOT / "outputs" / "scored_invoices.csv"
METRICS_CSV = ROOT / "outputs" / "evaluation_metrics.csv"
EXPORT_DIR  = ROOT / "powerbi_export"


def build_fact_invoices(scored):
    fact = scored[[
        "invoice_id", "vendor_id", "invoice_date", "amount_inr",
        "risk_score", "risk_level",
        "flag_duplicate", "flag_split_invoice", "flag_weekend_holiday",
        "flag_round_figure", "flag_outlier", "flag_count",
        "potential_leakage_inr", "exposure_at_risk_inr",
    ]].copy()
    fact["invoice_date"] = pd.to_datetime(fact["invoice_date"])
    fact["date_key"]     = fact["invoice_date"].dt.strftime("%Y%m%d").astype(int)
    return fact.drop(columns=["invoice_date"])


def build_dim_vendor(scored):
    return (
        scored[["vendor_id", "vendor_name", "department"]]
        .drop_duplicates(subset=["vendor_id"])
        .sort_values("vendor_id")
        .reset_index(drop=True)
    )


def build_dim_date(scored):
    min_dt = pd.to_datetime(scored["invoice_date"]).min()
    max_dt = pd.to_datetime(scored["invoice_date"]).max()

    dim = pd.DataFrame({"date": pd.date_range(min_dt, max_dt, freq="D")})
    dim["date_key"]    = dim["date"].dt.strftime("%Y%m%d").astype(int)
    dim["year"]        = dim["date"].dt.year
    dim["month"]       = dim["date"].dt.month
    dim["month_name"]  = dim["date"].dt.strftime("%B")
    dim["quarter"]     = dim["date"].dt.quarter
    dim["is_weekend"]  = (dim["date"].dt.dayofweek >= 5).astype(int)

    def fy(row):
        y, m = row["year"], row["month"]
        return f"FY {y}-{str(y+1)[-2:]}" if m >= 4 else f"FY {y-1}-{str(y)[-2:]}"

    dim["financial_year"] = dim.apply(fy, axis=1)
    dim["date"] = dim["date"].dt.strftime("%Y-%m-%d")
    return dim[["date_key", "date", "year", "month", "month_name", "quarter", "financial_year", "is_weekend"]]


def build_rule_summary(metrics):
    s = metrics[["rule", "gt_type", "flagged", "gt_count", "tp", "fp", "fn",
                  "precision", "recall", "f1"]].copy()
    s["precision_pct"] = (s["precision"] * 100).round(1)
    s["recall_pct"]    = (s["recall"]    * 100).round(1)
    s["f1_pct"]        = (s["f1"]        * 100).round(1)
    return s


def run_checks(fact, dim_vendor, dim_date):
    assert len(fact["invoice_id"].unique()) == len(fact), "Duplicate invoice_ids in fact"
    assert set(fact["vendor_id"]) <= set(dim_vendor["vendor_id"]), "vendor_ids missing from dim_vendor"
    assert set(fact["date_key"])  <= set(dim_date["date_key"]),    "date_keys missing from dim_date"
    print("  Self-checks passed.")


def main():
    EXPORT_DIR.mkdir(parents=True, exist_ok=True)

    scored  = pd.read_csv(SCORED_CSV)
    metrics = pd.read_csv(METRICS_CSV)

    fact       = build_fact_invoices(scored)
    dim_vendor = build_dim_vendor(scored)
    dim_date   = build_dim_date(scored)
    rule_sum   = build_rule_summary(metrics)

    run_checks(fact, dim_vendor, dim_date)

    fact.to_csv(      EXPORT_DIR / "fact_invoices.csv", index=False)
    dim_vendor.to_csv(EXPORT_DIR / "dim_vendor.csv",    index=False)
    dim_date.to_csv(  EXPORT_DIR / "dim_date.csv",      index=False)
    rule_sum.to_csv(  EXPORT_DIR / "rule_summary.csv",  index=False)

    print(f"\nExported to {EXPORT_DIR}:")
    for f in sorted(EXPORT_DIR.glob("*.csv")):
        rows = sum(1 for _ in open(f)) - 1
        print(f"  {f.name:<30} {rows:,} rows")


if __name__ == "__main__":
    main()
