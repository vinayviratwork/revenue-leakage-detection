"""
run_rules.py
Runs all 5 SQL detection rules against the SQLite database and prints
a summary: how many invoices each rule flagged and a quick overlap check
against ground_truth.csv.

Run from project root:
  python src/run_rules.py

Requires: data/db/invoices.db (run load_db.py first)
"""

import sqlite3
import yaml
import pandas as pd
from pathlib import Path

ROOT             = Path(__file__).parent.parent
DB_PATH          = ROOT / "data" / "db" / "invoices.db"
GROUND_TRUTH_CSV = ROOT / "data" / "ground_truth.csv"
CONFIG_YAML      = ROOT / "config.yaml"
SQL_DIR          = ROOT / "sql"

RULE_META = [
    {"file": "01_duplicates.sql",      "name": "Rule 1: Duplicates",        "gt_type": "duplicate",       "param_names": []},
    {"file": "02_split_invoices.sql",  "name": "Rule 2: Split Invoices",    "gt_type": "split_invoice",   "param_names": ["approval_limit"]},
    {"file": "03_weekend_holiday.sql", "name": "Rule 3: Weekend/Holiday",   "gt_type": "weekend_holiday", "param_names": []},
    {"file": "04_round_figure.sql",    "name": "Rule 4: Round Figure",      "gt_type": "round_figure",    "param_names": []},
    {"file": "05_outliers.sql",        "name": "Rule 5: Outliers",          "gt_type": "outlier",         "param_names": []},
]


def run_rule(conn, sql, params):
    cursor = conn.execute(sql, params)
    cols   = [d[0] for d in cursor.description]
    return pd.DataFrame(cursor.fetchall(), columns=cols)


def main():
    with open(CONFIG_YAML) as f:
        cfg = yaml.safe_load(f)

    gt_df = pd.read_csv(GROUND_TRUTH_CSV)

    if not DB_PATH.exists():
        raise FileNotFoundError(f"DB not found at {DB_PATH}. Run load_db.py first.")

    conn = sqlite3.connect(DB_PATH)

    print(f"\n{'='*60}")
    print("DETECTION RULE SUMMARY")
    print(f"  approval_limit: Rs {cfg['approval_limit']:,}")
    print(f"{'='*60}")

    all_flagged = set()

    for meta in RULE_META:
        sql    = (SQL_DIR / meta["file"]).read_text(encoding="utf-8")
        params = {"approval_limit": cfg["approval_limit"]} if "approval_limit" in meta["param_names"] else {}

        df          = run_rule(conn, sql, params)
        flagged_ids = set(df["invoice_id"])
        gt_ids      = set(gt_df.loc[gt_df["anomaly_type"] == meta["gt_type"], "invoice_id"])
        hits        = len(flagged_ids & gt_ids)
        all_flagged |= flagged_ids

        print(f"\n  {meta['name']}")
        print(f"    Flagged: {len(flagged_ids):,}  |  GT: {len(gt_ids)}  |  Hits: {hits}")
        if len(df):
            print(f"    Sample : {df['reason'].iloc[0]}")

    total = conn.execute("SELECT COUNT(*) FROM invoices").fetchone()[0]
    print(f"\n{'─'*60}")
    print(f"  Total invoices   : {total:,}")
    print(f"  Unique flagged   : {len(all_flagged):,}  ({len(all_flagged)/total*100:.1f}%)")
    print(f"{'='*60}\n")

    conn.close()


if __name__ == "__main__":
    main()
