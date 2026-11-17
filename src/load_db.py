"""
load_db.py
Loads invoices.csv and holidays.csv into a SQLite database.
Drops and recreates tables on every run so the script is idempotent.

Inputs:  data/raw/invoices.csv, data/holidays.csv
Output:  data/db/invoices.db

Run from project root:
  python src/load_db.py
"""

import sqlite3
import pandas as pd
from pathlib import Path

ROOT          = Path(__file__).parent.parent
INVOICES_CSV  = ROOT / "data" / "raw" / "invoices.csv"
HOLIDAYS_CSV  = ROOT / "data" / "holidays.csv"
DB_DIR        = ROOT / "data" / "db"
DB_PATH       = DB_DIR / "invoices.db"


def load_invoices(conn: sqlite3.Connection) -> int:
    df = pd.read_csv(INVOICES_CSV)
    df["invoice_date"] = pd.to_datetime(df["invoice_date"]).dt.strftime("%Y-%m-%d")
    df["payment_date"] = pd.to_datetime(df["payment_date"]).dt.strftime("%Y-%m-%d")

    conn.execute("DROP TABLE IF EXISTS invoices")
    df.to_sql("invoices", conn, index=False, if_exists="replace")

    conn.execute("CREATE INDEX IF NOT EXISTS idx_inv_vendor   ON invoices(vendor_id)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_inv_inv_date ON invoices(invoice_date)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_inv_pay_date ON invoices(payment_date)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_inv_vnd_date ON invoices(vendor_id, invoice_date)")
    conn.commit()
    return len(df)


def load_holidays(conn: sqlite3.Connection) -> int:
    df = pd.read_csv(HOLIDAYS_CSV)
    df["date"] = pd.to_datetime(df["date"]).dt.strftime("%Y-%m-%d")

    conn.execute("DROP TABLE IF EXISTS holidays")
    df.to_sql("holidays", conn, index=False, if_exists="replace")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_holidays_date ON holidays(date)")
    conn.commit()
    return len(df)


def main():
    DB_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)

    n_inv = load_invoices(conn)
    n_hol = load_holidays(conn)

    inv_count = conn.execute("SELECT COUNT(*) FROM invoices").fetchone()[0]
    vendors   = conn.execute("SELECT COUNT(DISTINCT vendor_id) FROM invoices").fetchone()[0]
    min_date  = conn.execute("SELECT MIN(invoice_date) FROM invoices").fetchone()[0]
    max_date  = conn.execute("SELECT MAX(invoice_date) FROM invoices").fetchone()[0]

    print(f"Loaded {inv_count:,} invoices, {n_hol} holidays")
    print(f"Vendors: {vendors}  |  Date range: {min_date} to {max_date}")
    print(f"DB: {DB_PATH}")
    conn.close()


if __name__ == "__main__":
    main()
