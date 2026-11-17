"""
generate_data.py
Generates ~20,000 synthetic vendor invoices for 150 vendors across 3 Indian
financial years (2022-04-01 to 2025-03-31), then injects five anomaly types.

Outputs:
  data/raw/invoices.csv    -- all invoices
  data/ground_truth.csv    -- one row per anomalous invoice

Run from project root:
  python src/generate_data.py
"""

import random
import numpy as np
import pandas as pd
from pathlib import Path
from datetime import timedelta

SEED = 42
random.seed(SEED)
np.random.seed(SEED)

ROOT              = Path(__file__).parent.parent
RAW_DIR           = ROOT / "data" / "raw"
DATA_DIR          = ROOT / "data"
INVOICES_PATH     = RAW_DIR / "invoices.csv"
GROUND_TRUTH_PATH = DATA_DIR / "ground_truth.csv"
HOLIDAYS_PATH     = DATA_DIR / "holidays.csv"

N_NORMAL        = 20_000
N_VENDORS       = 150
APPROVAL_LIMIT  = 50_000
START_DATE      = pd.Timestamp("2022-04-01")
END_DATE        = pd.Timestamp("2025-03-31")
ANOMALY_RATE    = 0.008

DEPARTMENTS = [
    "Finance", "IT", "Operations", "HR", "Marketing",
    "Procurement", "Legal", "Facilities", "R&D", "Admin",
]
PAYMENT_MODES        = ["NEFT", "RTGS", "UPI", "Cheque"]
PAYMENT_MODE_WEIGHTS = [0.45, 0.25, 0.20, 0.10]


def load_holidays() -> set:
    hdf = pd.read_csv(HOLIDAYS_PATH, parse_dates=["date"])
    return set(hdf["date"].dt.strftime("%Y-%m-%d"))


def build_vendor_catalogue(rng: np.random.Generator) -> pd.DataFrame:
    vendor_ids   = [f"VND{i:04d}" for i in range(1, N_VENDORS + 1)]
    vendor_names = [f"Vendor_{i:04d}_Ltd" for i in range(1, N_VENDORS + 1)]
    log_means    = rng.uniform(np.log(5_000), np.log(5_00_000), N_VENDORS)
    log_stds     = rng.uniform(0.3, 0.8, N_VENDORS)
    is_retainer  = rng.random(N_VENDORS) < 0.10
    home_dept    = rng.choice(DEPARTMENTS, N_VENDORS)

    return pd.DataFrame({
        "vendor_id":   vendor_ids,
        "vendor_name": vendor_names,
        "log_mean":    log_means,
        "log_std":     log_stds,
        "is_retainer": is_retainer,
        "home_dept":   home_dept,
    })


def to_weekday(date: pd.Timestamp) -> pd.Timestamp:
    while date.weekday() >= 5:
        date += timedelta(days=1)
    return date


def to_weekend(date: pd.Timestamp, rng: np.random.Generator) -> pd.Timestamp:
    days_to_sat = (5 - date.weekday()) % 7
    if days_to_sat == 0:
        days_to_sat = 7
    days_to_sun = days_to_sat + 1
    offset = int(rng.choice([days_to_sat, days_to_sun]))
    return date + timedelta(days=offset)


def payment_date_normal(invoice_date: pd.Timestamp,
                        rng: np.random.Generator,
                        holidays: set) -> pd.Timestamp:
    delta  = int(rng.integers(15, 46))
    pay_dt = invoice_date + timedelta(days=delta)
    pay_dt = to_weekday(pay_dt)

    if rng.random() < 0.02:
        pay_dt = to_weekend(pay_dt, rng)
    elif pay_dt.strftime("%Y-%m-%d") in holidays:
        if rng.random() >= 0.003:
            pay_dt = to_weekday(pay_dt + timedelta(days=1))

    return pay_dt


def sample_amount(vendor_row: pd.Series, rng: np.random.Generator) -> float:
    raw = float(np.exp(rng.normal(vendor_row["log_mean"], vendor_row["log_std"])))
    raw = max(raw, 500.0)

    if vendor_row["is_retainer"]:
        gran = max(100.0, round(raw * 0.01 / 100) * 100)
        raw  = round(raw / gran) * gran
        return float(max(raw, 500.0))
    else:
        return round(raw, 2)


def generate_normal(vendors: pd.DataFrame,
                    rng: np.random.Generator,
                    holidays: set) -> pd.DataFrame:
    total_days   = (END_DATE - START_DATE).days
    approver_ids = [f"APR{i:03d}" for i in range(1, 21)]
    records      = []

    for i in range(N_NORMAL):
        v_idx  = int(rng.integers(0, N_VENDORS))
        vendor = vendors.iloc[v_idx]

        inv_date = START_DATE + timedelta(days=int(rng.integers(0, total_days)))
        pay_date = payment_date_normal(inv_date, rng, holidays)
        amount   = sample_amount(vendor, rng)
        dept     = vendor["home_dept"] if rng.random() < 0.80 else rng.choice(DEPARTMENTS)

        records.append({
            "_orig_idx":     i,
            "_tag":          None,
            "vendor_id":     vendor["vendor_id"],
            "vendor_name":   vendor["vendor_name"],
            "invoice_date":  inv_date.date(),
            "payment_date":  pay_date.date(),
            "amount_inr":    amount,
            "approver_id":   rng.choice(approver_ids),
            "department":    dept,
            "payment_mode":  rng.choice(PAYMENT_MODES, p=PAYMENT_MODE_WEIGHTS),
            "_anomaly_type": None,
        })

    return pd.DataFrame(records)


def inject_duplicates(normal_df: pd.DataFrame,
                      rng: np.random.Generator,
                      holidays: set) -> tuple[list[dict], list[dict]]:
    n      = int(N_NORMAL * ANOMALY_RATE)
    sample = normal_df.sample(n=n, random_state=SEED)
    injected, truth = [], []

    for _, row in sample.iterrows():
        orig_inv_date = pd.Timestamp(row["invoice_date"])
        date_delta    = int(rng.integers(1, 8))
        new_inv_date  = orig_inv_date + timedelta(days=date_delta)
        new_pay_date  = payment_date_normal(new_inv_date, rng, holidays).date()
        tag = f"dup_{row['_orig_idx']}"

        injected.append({
            "_orig_idx":     None,
            "_tag":          tag,
            "vendor_id":     row["vendor_id"],
            "vendor_name":   row["vendor_name"],
            "invoice_date":  new_inv_date.date(),
            "payment_date":  new_pay_date,
            "amount_inr":    row["amount_inr"],
            "approver_id":   row["approver_id"],
            "department":    row["department"],
            "payment_mode":  row["payment_mode"],
            "_anomaly_type": "duplicate",
        })
        truth.append({
            "_tag":                  tag,
            "anomaly_type":          "duplicate",
            "group_id":              str(row["_orig_idx"]),
            "injected_extra_amount": row["amount_inr"],
        })

    return injected, truth


def inject_weekend_payments(normal_df: pd.DataFrame,
                            rng: np.random.Generator) -> tuple[pd.DataFrame, list[dict]]:
    n      = int(N_NORMAL * ANOMALY_RATE)
    sampled = normal_df.sample(n=n, random_state=SEED + 1)

    all_dates    = pd.date_range(START_DATE, END_DATE, freq="D")
    weekend_pool = [d for d in all_dates if d.weekday() >= 5]

    mutated_df = normal_df.copy()
    truth      = []

    for i, (idx, row) in enumerate(sampled.iterrows()):
        new_pay = rng.choice(weekend_pool).date()
        mutated_df.at[idx, "payment_date"]    = new_pay
        mutated_df.at[idx, "_anomaly_type"]   = "weekend_holiday"
        mutated_df.at[idx, "_tag"]            = f"wknd_{i}"

        truth.append({
            "_tag":                  f"wknd_{i}",
            "anomaly_type":          "weekend_holiday",
            "group_id":              "",
            "injected_extra_amount": 0.0,
        })

    return mutated_df, truth


def inject_split_invoices(normal_df: pd.DataFrame,
                          vendors: pd.DataFrame,
                          rng: np.random.Generator,
                          holidays: set) -> tuple[list[dict], list[dict]]:
    n_clusters   = int(N_NORMAL * ANOMALY_RATE)
    approver_ids = [f"APR{i:03d}" for i in range(1, 21)]
    total_days   = (END_DATE - START_DATE).days
    injected, truth = [], []

    for cluster_idx in range(n_clusters):
        v_idx        = int(rng.integers(0, N_VENDORS))
        vendor       = vendors.iloc[v_idx]
        cluster_size = int(rng.integers(2, 5))
        base_date    = START_DATE + timedelta(days=int(rng.integers(0, total_days - 5)))
        approver     = rng.choice(approver_ids)
        department   = vendor["home_dept"]
        group_id     = f"split_cluster_{cluster_idx:04d}"

        for j in range(cluster_size):
            pct      = rng.uniform(0.80, 0.98)
            amount   = round(APPROVAL_LIMIT * pct, 2)
            inv_date = (base_date + timedelta(days=int(rng.integers(0, 4)))).date()
            pay_date = payment_date_normal(pd.Timestamp(inv_date), rng, holidays).date()
            tag      = f"split_{cluster_idx}_{j}"

            injected.append({
                "_orig_idx":     None,
                "_tag":          tag,
                "vendor_id":     vendor["vendor_id"],
                "vendor_name":   vendor["vendor_name"],
                "invoice_date":  inv_date,
                "payment_date":  pay_date,
                "amount_inr":    amount,
                "approver_id":   approver,
                "department":    department,
                "payment_mode":  rng.choice(PAYMENT_MODES, p=PAYMENT_MODE_WEIGHTS),
                "_anomaly_type": "split_invoice",
            })
            truth.append({
                "_tag":                  tag,
                "anomaly_type":          "split_invoice",
                "group_id":              group_id,
                "injected_extra_amount": amount,
            })

    return injected, truth


def inject_round_figures(normal_df: pd.DataFrame,
                         vendors: pd.DataFrame,
                         rng: np.random.Generator) -> tuple[list[dict], list[dict]]:
    n            = int(N_NORMAL * ANOMALY_RATE)
    retainer_ids = set(vendors.loc[vendors["is_retainer"], "vendor_id"])
    pool         = normal_df[~normal_df["vendor_id"].isin(retainer_ids)]
    sample       = pool.sample(n=n, random_state=SEED + 2)
    injected, truth = [], []

    for i, (_, row) in enumerate(sample.iterrows()):
        mult   = int(rng.integers(2, 10))
        amount = float(mult * 10_000)
        tag    = f"rnd_{i}"

        injected.append({
            "_orig_idx":     None,
            "_tag":          tag,
            "vendor_id":     row["vendor_id"],
            "vendor_name":   row["vendor_name"],
            "invoice_date":  row["invoice_date"],
            "payment_date":  row["payment_date"],
            "amount_inr":    amount,
            "approver_id":   row["approver_id"],
            "department":    row["department"],
            "payment_mode":  row["payment_mode"],
            "_anomaly_type": "round_figure",
        })
        truth.append({
            "_tag":                  tag,
            "anomaly_type":          "round_figure",
            "group_id":              "",
            "injected_extra_amount": 0.0,
        })

    return injected, truth


def inject_outliers(normal_df: pd.DataFrame,
                    rng: np.random.Generator) -> tuple[list[dict], list[dict]]:
    n            = int(N_NORMAL * ANOMALY_RATE)
    sample       = normal_df.sample(n=n, random_state=SEED + 3)
    vendor_means = normal_df.groupby("vendor_id")["amount_inr"].mean()
    injected, truth = [], []

    for i, (_, row) in enumerate(sample.iterrows()):
        vendor_mean = float(vendor_means.get(row["vendor_id"], row["amount_inr"]))
        multiplier  = rng.uniform(4.0, 8.0)
        amount      = round(vendor_mean * multiplier, 2)
        tag         = f"out_{i}"

        injected.append({
            "_orig_idx":     None,
            "_tag":          tag,
            "vendor_id":     row["vendor_id"],
            "vendor_name":   row["vendor_name"],
            "invoice_date":  row["invoice_date"],
            "payment_date":  row["payment_date"],
            "amount_inr":    amount,
            "approver_id":   row["approver_id"],
            "department":    row["department"],
            "payment_mode":  row["payment_mode"],
            "_anomaly_type": "outlier",
        })
        truth.append({
            "_tag":                  tag,
            "anomaly_type":          "outlier",
            "group_id":              "",
            "injected_extra_amount": round(amount - vendor_mean, 2),
        })

    return injected, truth


def main():
    rng      = np.random.default_rng(SEED)
    holidays = load_holidays()

    print("Building vendor catalogue...")
    vendors = build_vendor_catalogue(rng)

    print(f"Generating {N_NORMAL:,} normal invoices...")
    normal_df = generate_normal(vendors, rng, holidays)

    print("Injecting anomalies...")
    normal_df, wknd_truth = inject_weekend_payments(normal_df, rng)

    dup_rows,   dup_truth   = inject_duplicates(normal_df, rng, holidays)
    split_rows, split_truth = inject_split_invoices(normal_df, vendors, rng, holidays)
    rnd_rows,   rnd_truth   = inject_round_figures(normal_df, vendors, rng)
    out_rows,   out_truth   = inject_outliers(normal_df, rng)

    normal_records = normal_df.to_dict("records")
    all_rows    = normal_records + dup_rows + split_rows + rnd_rows + out_rows
    invoices_df = pd.DataFrame(all_rows)
    invoices_df = invoices_df.sample(frac=1, random_state=SEED).reset_index(drop=True)
    invoices_df.insert(0, "invoice_id",
                       [f"INV{i:06d}" for i in range(1, len(invoices_df) + 1)])

    tag_to_inv_id = (
        invoices_df[invoices_df["_tag"].notna()]
        .set_index("_tag")["invoice_id"]
        .to_dict()
    )

    all_truth = dup_truth + split_truth + wknd_truth + rnd_truth + out_truth
    for t in all_truth:
        t["invoice_id"] = tag_to_inv_id[t["_tag"]]

    ground_truth_df = pd.DataFrame(all_truth)[
        ["invoice_id", "anomaly_type", "group_id", "injected_extra_amount"]
    ]

    invoices_df = invoices_df.drop(columns=["_orig_idx", "_tag", "_anomaly_type"])

    RAW_DIR.mkdir(parents=True, exist_ok=True)
    invoices_df.to_csv(INVOICES_PATH, index=False)
    ground_truth_df.to_csv(GROUND_TRUTH_PATH, index=False)

    gt_ids   = set(ground_truth_df["invoice_id"])
    wknd_ids = set(ground_truth_df.loc[
        ground_truth_df["anomaly_type"] == "weekend_holiday", "invoice_id"
    ])
    new_anomaly_ids = gt_ids - wknd_ids

    print(f"\nTotal invoices written : {len(invoices_df):,}")
    print(f"Ground-truth rows      : {len(ground_truth_df):,}")
    print(f"Invoice date range     : {pd.to_datetime(invoices_df['invoice_date']).min().date()} "
          f"to {pd.to_datetime(invoices_df['invoice_date']).max().date()}")
    print(f"\nFiles written:\n  {INVOICES_PATH}\n  {GROUND_TRUTH_PATH}")


if __name__ == "__main__":
    main()
