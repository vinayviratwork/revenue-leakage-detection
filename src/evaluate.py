"""
evaluate.py
Compares rule flags in scored_invoices.csv against ground_truth.csv
to compute precision, recall, and F1 per rule.

Outputs:
  outputs/evaluation_report.md
  outputs/evaluation_metrics.csv

Run from project root:
  python src/evaluate.py  (run score.py first)
"""

import pandas as pd
from pathlib import Path

ROOT         = Path(__file__).parent.parent
SCORED_CSV   = ROOT / "outputs" / "scored_invoices.csv"
GT_CSV       = ROOT / "data" / "ground_truth.csv"
REPORT_PATH  = ROOT / "outputs" / "evaluation_report.md"
METRICS_CSV  = ROOT / "outputs" / "evaluation_metrics.csv"

RULE_MAP = [
    ("flag_duplicate",       "duplicate",       "Rule 1: Duplicates"),
    ("flag_split_invoice",   "split_invoice",   "Rule 2: Split Invoices"),
    ("flag_weekend_holiday", "weekend_holiday", "Rule 3: Weekend/Holiday"),
    ("flag_round_figure",    "round_figure",    "Rule 4: Round Figure"),
    ("flag_outlier",         "outlier",         "Rule 5: Outliers"),
]


def safe_div(num, den):
    return num / den if den > 0 else 0.0


def compute_metrics(scored, gt):
    results = []
    for flag_col, gt_type, label in RULE_MAP:
        flagged_ids = set(scored.loc[scored[flag_col] == 1, "invoice_id"])
        gt_ids      = set(gt.loc[gt["anomaly_type"] == gt_type, "invoice_id"])

        tp = len(flagged_ids & gt_ids)
        fp = len(flagged_ids - gt_ids)
        fn = len(gt_ids - flagged_ids)

        precision = safe_div(tp, tp + fp)
        recall    = safe_div(tp, tp + fn)
        f1        = safe_div(2 * precision * recall, precision + recall)

        results.append({
            "rule": label, "flag_col": flag_col, "gt_type": gt_type,
            "flagged": len(flagged_ids), "tp": tp, "fp": fp, "fn": fn,
            "gt_count": len(gt_ids),
            "precision": round(precision, 4),
            "recall":    round(recall, 4),
            "f1":        round(f1, 4),
        })
    return results


def compute_overall(scored, gt):
    any_flagged = set(scored.loc[scored["flag_count"] > 0, "invoice_id"])
    all_gt      = set(gt["invoice_id"])

    tp = len(any_flagged & all_gt)
    fp = len(any_flagged - all_gt)
    fn = len(all_gt - any_flagged)

    precision = safe_div(tp, tp + fp)
    recall    = safe_div(tp, tp + fn)
    f1        = safe_div(2 * precision * recall, precision + recall)

    return {
        "flagged_any": len(any_flagged), "gt_total": len(all_gt),
        "tp": tp, "fp": fp, "fn": fn,
        "precision": round(precision, 4),
        "recall":    round(recall, 4),
        "f1":        round(f1, 4),
    }


def compute_leakage_split(scored, gt):
    gt_ids     = set(gt["invoice_id"])
    tp_mask    = scored["invoice_id"].isin(gt_ids)
    leakage_tp = scored.loc[tp_mask,  "potential_leakage_inr"].sum()
    leakage_fp = scored.loc[~tp_mask, "potential_leakage_inr"].sum()
    return {
        "total_potential":  leakage_tp + leakage_fp,
        "from_tp":          leakage_tp,
        "from_fp":          leakage_fp,
        "exposure_total":   scored["exposure_at_risk_inr"].sum(),
        "injected_total":   gt["injected_extra_amount"].sum(),
        "injected_by_type": gt.groupby("anomaly_type")["injected_extra_amount"].sum(),
    }


def build_report(metrics, overall, leakage, scored, gt):
    high_ct = (scored["risk_level"] == "HIGH").sum()
    med_ct  = (scored["risk_level"] == "MEDIUM").sum()
    low_ct  = (scored["risk_level"] == "LOW").sum()
    total   = len(scored)

    lines = ["# Evaluation Report", ""]
    lines.append(
        "Precision, recall and F1 per rule, computed against `data/ground_truth.csv`. "
        "Data is synthetic so recall figures are higher than expected on real data — "
        "anomalies were injected to match rule conditions exactly."
    )
    lines.append("")

    lines.append("## Per-Rule Metrics")
    lines.append("")
    lines.append("| Rule | Flagged | GT | TP | FP | FN | Precision | Recall | F1 |")
    lines.append("|---|---|---|---|---|---|---|---|---|")
    for m in metrics:
        lines.append(
            f"| {m['rule']} | {m['flagged']:,} | {m['gt_count']:,} "
            f"| {m['tp']:,} | {m['fp']:,} | {m['fn']:,} "
            f"| {m['precision']:.1%} | {m['recall']:.1%} | {m['f1']:.1%} |"
        )
    lines.append("")

    lines.append("## Overall")
    lines.append("")
    lines.append("| Metric | Value |")
    lines.append("|---|---|")
    lines.append(f"| Total invoices | {total:,} |")
    lines.append(f"| Flagged (any rule) | {overall['flagged_any']:,} |")
    lines.append(f"| Ground-truth anomalies | {overall['gt_total']:,} |")
    lines.append(f"| TP | {overall['tp']:,} |")
    lines.append(f"| FP | {overall['fp']:,} |")
    lines.append(f"| FN | {overall['fn']:,} |")
    lines.append(f"| Precision | {overall['precision']:.1%} |")
    lines.append(f"| Recall | {overall['recall']:.1%} |")
    lines.append(f"| F1 | {overall['f1']:.1%} |")
    lines.append("")

    lines.append("## Risk Level Distribution")
    lines.append("")
    lines.append("| Risk Level | Count | % |")
    lines.append("|---|---|---|")
    lines.append(f"| HIGH (score >= 40) | {high_ct:,} | {high_ct/total:.1%} |")
    lines.append(f"| MEDIUM (20–39) | {med_ct:,} | {med_ct/total:.1%} |")
    lines.append(f"| LOW (< 20) | {low_ct:,} | {low_ct/total:.1%} |")
    lines.append("")

    lines.append("## Potential Leakage: TP vs FP Split")
    lines.append("")
    lines.append("| Source | Amount (Rs) |")
    lines.append("|---|---|")
    lines.append(f"| From true positives | {leakage['from_tp']:,.0f} |")
    lines.append(f"| From false positives (cleared after audit) | {leakage['from_fp']:,.0f} |")
    lines.append(f"| **Total flagged** | **{leakage['total_potential']:,.0f}** |")
    lines.append(f"| Exposure at risk | {leakage['exposure_total']:,.0f} |")
    lines.append("")

    lines.append("## Limitations")
    lines.append("")
    for m in metrics:
        lines.append(f"**{m['rule']}** — "
                     f"Precision {m['precision']:.1%} | Recall {m['recall']:.1%} | F1 {m['f1']:.1%}. "
                     f"FP: {m['fp']:,}  FN: {m['fn']:,}")
        lines.append("")

    lines.append(
        "Rule 3 (Weekend/Holiday) precision is low because ~400 normal invoices naturally "
        "fall on weekends due to the 15–45 day payment lag. "
        "Rule 5 (Outliers) precision is low because lognormal distributions have heavy upper "
        "tails — many normal invoices for high-variance vendors exceed mean + 3σ."
    )
    lines.append("")
    lines.append("*Generated by src/evaluate.py*")

    return "\n".join(lines)


def main():
    scored = pd.read_csv(SCORED_CSV)
    gt     = pd.read_csv(GT_CSV)

    metrics = compute_metrics(scored, gt)
    overall = compute_overall(scored, gt)
    leakage = compute_leakage_split(scored, gt)

    overlap = scored[(scored["potential_leakage_inr"] > 0) & (scored["exposure_at_risk_inr"] > 0)]
    assert len(overlap) == 0, f"{len(overlap)} invoices in both leakage columns"

    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text(build_report(metrics, overall, leakage, scored, gt), encoding="utf-8")

    pd.DataFrame([{k: v for k, v in m.items() if k not in ("flag_col", "gt_type")}
                  for m in metrics]).to_csv(METRICS_CSV, index=False)

    print(f"\n{'='*60}")
    print(f"{'Rule':<30} {'Prec':>6} {'Rec':>6} {'F1':>6}")
    print(f"{'─'*60}")
    for m in metrics:
        print(f"{m['rule']:<30} {m['precision']:>5.1%} {m['recall']:>5.1%} {m['f1']:>5.1%}")
    print(f"{'─'*60}")
    print(f"{'OVERALL':<30} {overall['precision']:>5.1%} {overall['recall']:>5.1%} {overall['f1']:>5.1%}")
    print(f"\nLeakage from TP: Rs {leakage['from_tp']:,.0f}  |  FP: Rs {leakage['from_fp']:,.0f}")
    print(f"Reports: {REPORT_PATH.name}, {METRICS_CSV.name}")


if __name__ == "__main__":
    main()
