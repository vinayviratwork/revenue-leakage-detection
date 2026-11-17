# Revenue Leakage Detection

> **Audit-analytics portfolio project** — automatically detects suspicious vendor invoice patterns in accounts-payable data using SQL detection rules, risk scoring, a Streamlit dashboard, and a Power BI star-schema export.

---

## Overview

A mid-size company paying thousands of vendor invoices every year is exposed to quiet cash leakage through duplicate payments, approval-limit bypasses, statistical outliers, and suspicious payment timing. Manual review is too slow to catch all of them consistently.

This project builds an end-to-end detection pipeline on 20,951 synthetic invoices across 150 vendors over three Indian financial years (FY 2022–23 to FY 2024–25). Five rule-based SQL detectors flag anomalies, a risk-scoring engine prioritises them (HIGH / MEDIUM / LOW), and an interactive Streamlit dashboard surfaces the top risks for auditor review.

**Tech stack:** Python · SQL (SQLite) · Streamlit · Plotly · Pandas · Power BI  
**Lines of code:** ~1,800 Python · ~200 SQL · 41 automated tests (all passing)

---

## Key Results

| Rule | Flagged | Precision | Recall | F1 |
|---|---|---|---|---|
| Rule 1: Duplicates | 177 | 90.4% | 100.0% | 95.0% |
| Rule 2: Split Invoices | 489 | 96.3% | 100.0% | 98.1% |
| Rule 3: Weekend / Holiday | 591 | 27.1% | 100.0% | 42.6% |
| Rule 4: Round Figure | 200 | 80.0% | 100.0% | 88.9% |
| Rule 5: Outliers | 392 | 39.8% | 97.5% | 56.5% |
| **Overall** | **1,731** | **63.9%** | **99.6%** | **77.9%** |

| Financial Metric | Amount |
|---|---|
| Potential leakage flagged (before audit review) | Rs 15.52 Cr |
| — from confirmed true positives | Rs 8.97 Cr |
| — from false positives (cleared after audit) | Rs 6.56 Cr |
| Exposure at risk (split / round / weekend) | Rs 8.83 Cr |
| HIGH risk invoices (score ≥ 40) | 253 |
| MEDIUM risk invoices (score 20–39) | 741 |
| Total invoices flagged | 1,731 of 20,951 (8.3%) |

---

## Project Structure

```
revenue-leakage-detection/
├── app.py                      Streamlit dashboard (run from root)
├── config.yaml                 Approval limit, rule weights, thresholds
├── requirements.txt            Pinned Python dependencies
├── DATA_DICTIONARY.md          Column definitions for all datasets
├── MY_DESIGN.md                Design decisions and architecture notes
├── EXPLAINING.md               Plain-language explanation + interview Q&A
├── POWERBI_GUIDE.md            Step-by-step Power BI Desktop guide
│
├── data/
│   ├── raw/invoices.csv        20,951 synthetic invoices
│   ├── ground_truth.csv        1,111 anomaly labels
│   ├── holidays.csv            40 Indian national holidays (FY22–25)
│   └── db/invoices.db          SQLite database (regenerated; not in git)
│
├── sql/
│   ├── 01_duplicates.sql
│   ├── 02_split_invoices.sql
│   ├── 03_weekend_holiday.sql
│   ├── 04_round_figure.sql
│   └── 05_outliers.sql
│
├── src/
│   ├── generate_data.py        Stage A: synthetic data generator (seed=42)
│   ├── load_db.py              Stage B: CSV → SQLite loader
│   ├── run_rules.py            Stage B: run rules, print counts
│   ├── score.py                Stage C: risk scoring + vendor summary
│   ├── evaluate.py             Stage C: precision / recall / F1
│   └── export_powerbi.py       Stage D: star-schema CSV export
│
├── outputs/
│   ├── scored_invoices.csv     Invoice-level scores and flags
│   ├── vendor_risk.csv         Vendor-level risk summary
│   ├── evaluation_metrics.csv  Per-rule precision / recall / F1
│   └── evaluation_report.md    Full evaluation with limitations analysis
│
├── powerbi_export/
│   ├── fact_invoices.csv
│   ├── dim_vendor.csv
│   ├── dim_date.csv
│   └── rule_summary.csv
│
└── tests/
    ├── test_rules.py           SQL rule unit tests (26 tests)
    └── test_score.py           Scoring logic tests (15 tests)
```

---

## How to Run

All commands run from the project root. Steps must be run in order.

```bash
# 1. Install dependencies
pip install -r requirements.txt

# 2. Generate synthetic data  (~5 seconds, fully reproducible seed=42)
python src/generate_data.py

# 3. Load into SQLite
python src/load_db.py

# 4. Run detection rules (sanity check output)
python src/run_rules.py

# 5. Score invoices and build vendor risk table
python src/score.py

# 6. Evaluate against ground truth
python src/evaluate.py

# 7. Export Power BI star-schema files
python src/export_powerbi.py

# 8. Launch interactive Streamlit dashboard
streamlit run app.py

# 9. Run all tests
python -m pytest tests/ -v
```

> **Note:** Steps 2–7 have already been run. `outputs/` and `powerbi_export/` contain pre-computed results. You can jump straight to step 8 to see the dashboard.

---

## Pipeline Architecture

```
Raw Data          Detection          Scoring           Outputs
─────────         ─────────          ───────           ───────
generate_data.py  01_duplicates.sql  score.py          Streamlit dashboard
     │            02_split_inv.sql        │             Power BI CSVs
     ▼            03_weekend.sql          ▼             evaluation_report.md
invoices.csv      04_round_fig.sql   scored_invoices.csv
     │            05_outliers.sql    vendor_risk.csv
     ▼                  │
load_db.py         run_rules.py ──► evaluate.py ──► evaluation_metrics.csv
     │
invoices.db
```

---

## Detection Rules

| # | Rule | Signal | Weight |
|---|---|---|---|
| 1 | **Duplicate payment** | Same vendor + amount within 7 days | 40 pts |
| 2 | **Split invoice** | Same vendor + approver, amounts 80–98% of approval limit, within 3 days | 30 pts |
| 3 | **Weekend / holiday payment** | Payment date falls on Saturday, Sunday, or public holiday | 10 pts |
| 4 | **Round figure** | Amount is an exact multiple of ₹10,000 and ≥ ₹20,000, vendor's round-rate < 15% | 10 pts |
| 5 | **Statistical outlier** | Amount > vendor mean + 3 × std dev (vendors with ≥ 10 invoices only) | 20 pts |

Risk score = sum of triggered rule weights, capped at 100.

---

## Risk Scoring

```
Score ≥ 40  →  HIGH    (escalate to auditor immediately)
Score 20–39 →  MEDIUM  (review recommended)
Score < 20  →  LOW     (monitor)
```

An invoice flagged for both a duplicate and an outlier is counted once under the duplicate (highest confirmed-loss rule). Potential leakage and exposure at risk are mutually exclusive by construction — no invoice appears in both.

---

## Dashboard Features

The Streamlit dashboard (`app.py`) has two tabs:

**Dashboard tab**
- KPI row: total invoices, total spend, potential leakage, exposure at risk, % flagged
- Sidebar filters: risk level, department, invoice date range
- Bar chart: potential leakage and exposure broken down by rule
- Line chart: monthly trend of flagged invoice amounts
- Top 10 risky vendors table
- Top 20 suspicious invoices table with risk scores and triggered rules

**Model Quality tab**
- Per-rule precision, recall, F1 table
- Grouped bar chart comparing all three metrics across rules
- Honest disclaimer about synthetic-data inflation of recall

---

## Power BI Export

`powerbi_export/` contains a star schema ready to load into Power BI Desktop:

| Table | Description |
|---|---|
| `fact_invoices.csv` | One row per invoice with all flag columns, risk score, leakage amounts |
| `dim_vendor.csv` | Vendor dimension |
| `dim_date.csv` | Date dimension with Indian financial year, quarter, month, is_weekend |
| `rule_summary.csv` | Per-rule precision / recall / F1 for a summary visual |

See `POWERBI_GUIDE.md` for step-by-step loading instructions.

---

## Honest Limitations

**Synthetic data only.** The pipeline has never been run on real company data.

**Recall is inflated.** Anomalies were injected to match rule conditions exactly. On real, messier data, expect recall to be 20–40 percentage points lower.

**Rule 3 precision is 27.1%.** About 400 normal invoices naturally fall on weekends due to the 15–45 day payment lag. Payment timestamps (hour of day) would improve precision significantly.

**Rule 5 precision is 39.8%.** Lognormal invoice-amount distributions have heavy upper tails, so many legitimate invoices for high-variance vendors exceed the mean + 3σ threshold. Switching to median + 3 × MAD would reduce false positives.

**Simple rule-based system.** No machine learning. Rules cannot adapt to new fraud patterns, learn vendor-specific behaviour, or weight contextual signals such as approver history.

Full analysis is in `outputs/evaluation_report.md`.

---

## Future Work

- Replace mean + 3σ with median + 3 × MAD for a more robust outlier rule
- Add invoice reference numbers to eliminate retainer-vendor false positives in Rule 1
- Extend the holiday list to cover state-specific and bank holidays
- Add a business-hours rule: flag approvals outside 9 am–6 pm on weekdays
- Train an isolation forest or logistic regression model on top of the rule flags as a second-stage classifier
- Connect to a real ERP export via API instead of synthetic data

---

## About This Project

Built as a portfolio project to demonstrate end-to-end data-engineering and analytics skills: data modelling, SQL query design, Python pipeline architecture, statistical anomaly detection, evaluation methodology, and dashboard development.

Problem framing, rule design, scoring logic, and analysis decisions are my own. Built with AI coding assistance (Kiro IDE).

*Data is entirely synthetic. No real company data was used.*
