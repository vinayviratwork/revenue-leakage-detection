"""
score.py
Runs the 5 SQL rules, assigns a risk score and risk level to each invoice,
and builds a vendor-level risk summary.

Scoring:
  risk_score = sum of triggered rule weights, capped at 100
  HIGH   >= 40  |  MEDIUM >= 20  |  LOW < 20

Leakage definitions:
  potential_leakage_inr  -- duplicate: full amount; outlier (not dup): excess over vendor mean
  exposure_at_risk_inr   -- split/round/weekend only invoices: full amount
  The two columns never overlap.

Outputs: outputs/scored_invoices.csv, outputs/vendor_risk.csv

Run from project root:
  python src/score.py
"""

import sqlite3
import yaml
import pandas as pd
from pathlib import Path

ROOT         = Path(__file__).parent.parent
DB_PATH      = ROOT / "data" / "db" / "invoices.db"
CONFIG_PATH  = ROOT / "config.yaml"
SQL_DIR      = ROOT / "sql"
OUTPUTS_DIR  = ROOT / "outputs"
SCORED_CSV   = OUTPUTS_DIR / "scored_invoices.csv"
VENDOR_CSV   = OUTPUTS_DIR / "vendor_risk.csv"


def load_config():
    with open(CONFIG_PATH) as f:
        return yaml.safe_load(f)


def run_rule(conn, sql_file, params):
    sql = (SQL_DIR / sql_file).read_text(encoding="utf-8")
    return {row[0] for row in conn.execute(sql, params).fetchall()}


def get_vendor_means(conn):
    rows = conn.execute("SELECT vendor_id, AVG(amount_inr) FROM invoices GROUP BY vendor_id").fetchall()
    return {r[0]: r[1] for r in rows}


def build_scored_invoices(conn, cfg):
    weights = cfg["rule_weights"]
    high_t  = cfg["high_risk_threshold"]
    med_t   = cfg["medium_risk_threshold"]
    al      = cfg["approval_limit"]

    inv = pd.read_sql_query("SELECT * FROM invoices", conn)

    flag_dup   = run_rule(conn, "01_duplicates.sql",      {})
    flag_split = run_rule(conn, "02_split_invoices.sql",  {"approval_limit": al})
    flag_wknd  = run_rule(conn, "03_weekend_holiday.sql", {})
    flag_rnd   = run_rule(conn, "04_round_figure.sql",    {})
    flag_out   = run_rule(conn, "05_outliers.sql",        {})

    inv["flag_duplicate"]       = inv["invoice_id"].isin(flag_dup).astype(int)
    inv["flag_split_invoice"]   = inv["invoice_id"].isin(flag_split).astype(int)
    inv["flag_weekend_holiday"] = inv["invoice_id"].isin(flag_wknd).astype(int)
    inv["flag_round_figure"]    = inv["invoice_id"].isin(flag_rnd).astype(int)
    inv["flag_outlier"]         = inv["invoice_id"].isin(flag_out).astype(int)

    inv["flag_count"] = (
        inv["flag_duplicate"] + inv["flag_split_invoice"] +
        inv["flag_weekend_holiday"] + inv["flag_round_figure"] +
        inv["flag_outlier"]
    )

    inv["risk_score"] = (
        inv["flag_duplicate"]       * weights["duplicate"]       +
        inv["flag_split_invoice"]   * weights["split_invoice"]   +
        inv["flag_weekend_holiday"] * weights["weekend_holiday"] +
        inv["flag_round_figure"]    * weights["round_figure"]    +
        inv["flag_outlier"]         * weights["outlier"]
    ).clip(upper=100)

    inv["risk_level"] = inv["risk_score"].apply(
        lambda s: "HIGH" if s >= high_t else ("MEDIUM" if s >= med_t else "LOW")
    )

    vendor_means = get_vendor_means(conn)
    inv["_vendor_mean"] = inv["vendor_id"].map(vendor_means)

    potential = []
    for _, row in inv.iterrows():
        if row["flag_duplicate"] == 1:
            potential.append(row["amount_inr"])
        elif row["flag_outlier"] == 1:
            potential.append(max(row["amount_inr"] - row["_vendor_mean"], 0.0))
        else:
            potential.append(0.0)
    inv["potential_leakage_inr"] = potential

    exposure = []
    for _, row in inv.iterrows():
        if row["flag_duplicate"] == 1 or row["flag_outlier"] == 1:
            exposure.append(0.0)
        elif row["flag_split_invoice"] == 1 or row["flag_round_figure"] == 1 or row["flag_weekend_holiday"] == 1:
            exposure.append(row["amount_inr"])
        else:
            exposure.append(0.0)
    inv["exposure_at_risk_inr"] = exposure

    return inv.drop(columns=["_vendor_mean"])


def build_vendor_risk(scored):
    vendor_grp = scored.groupby(["vendor_id", "vendor_name"]).agg(
        invoice_count         = ("invoice_id",           "count"),
        flagged_count         = ("flag_count",            lambda x: (x > 0).sum()),
        total_spend_inr       = ("amount_inr",            "sum"),
        flagged_amount_inr    = ("amount_inr",            lambda x: x[scored.loc[x.index, "flag_count"] > 0].sum()),
        potential_leakage_inr = ("potential_leakage_inr", "sum"),
        exposure_at_risk_inr  = ("exposure_at_risk_inr",  "sum"),
        avg_risk_score        = ("risk_score",            "mean"),
        max_risk_score        = ("risk_score",            "max"),
    ).reset_index()

    vendor_grp["flag_rate_pct"]  = (vendor_grp["flagged_count"] / vendor_grp["invoice_count"] * 100).round(2)
    vendor_grp["avg_risk_score"] = vendor_grp["avg_risk_score"].round(2)
    vendor_grp["risk_tier"]      = vendor_grp["max_risk_score"].apply(
        lambda s: "HIGH" if s >= 40 else ("MEDIUM" if s >= 20 else "LOW")
    )
    return vendor_grp.sort_values("potential_leakage_inr", ascending=False)


def run_self_checks(scored, vendor):
    assert scored["invoice_id"].duplicated().sum() == 0, "Duplicate invoice_ids found"
    assert scored["risk_score"].max() <= 100, "Risk score exceeds 100"
    assert ((scored["risk_level"] == "HIGH") == (scored["risk_score"] >= 40)).all()
    assert ((scored["risk_level"] == "MEDIUM") == ((scored["risk_score"] >= 20) & (scored["risk_score"] < 40))).all()
    overlap = scored[(scored["potential_leakage_inr"] > 0) & (scored["exposure_at_risk_inr"] > 0)]
    assert len(overlap) == 0, f"{len(overlap)} invoices in both leakage columns"
    assert abs(scored["potential_leakage_inr"].sum() - vendor["potential_leakage_inr"].sum()) < 0.01
    print("  All self-checks passed.")


def main():
    OUTPUTS_DIR.mkdir(parents=True, exist_ok=True)
    cfg  = load_config()
    conn = sqlite3.connect(DB_PATH)

    scored = build_scored_invoices(conn, cfg)
    vendor = build_vendor_risk(scored)
    run_self_checks(scored, vendor)

    scored.to_csv(SCORED_CSV, index=False)
    vendor.to_csv(VENDOR_CSV, index=False)

    total    = len(scored)
    flagged  = (scored["flag_count"] > 0).sum()
    high_ct  = (scored["risk_level"] == "HIGH").sum()
    med_ct   = (scored["risk_level"] == "MEDIUM").sum()

    print(f"\nScored {total:,} invoices  |  Flagged: {flagged:,} ({flagged/total*100:.1f}%)")
    print(f"HIGH: {high_ct:,}  MEDIUM: {med_ct:,}")
    print(f"Potential leakage : Rs {scored['potential_leakage_inr'].sum():,.0f}")
    print(f"Exposure at risk  : Rs {scored['exposure_at_risk_inr'].sum():,.0f}")

    conn.close()


if __name__ == "__main__":
    main()
