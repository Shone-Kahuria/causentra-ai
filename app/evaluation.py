"""Versioned, fixed synthetic rules baseline. No model claims are inferred here."""
from __future__ import annotations

import json

DATASET_VERSION = "synthetic-rules-v1"
CASES = [
    {"id": "delay-3", "delay_days": 3, "daily_demand": 8, "label_risk": True},
    {"id": "delay-1", "delay_days": 1, "daily_demand": 8, "label_risk": False},
    {"id": "on-time", "delay_days": 0, "daily_demand": 8, "label_risk": False},
    {"id": "demand-spike", "delay_days": 0, "daily_demand": 20, "label_risk": True},
    {"id": "delay-4-low-demand", "delay_days": 4, "daily_demand": 3, "label_risk": False},
    {"id": "delay-2", "delay_days": 2, "daily_demand": 8, "label_risk": True},
    {"id": "payment-failure", "delay_days": 0, "daily_demand": 8, "label_risk": True},
]


def evaluate():
    rows = []
    for case in CASES:
        available = 20 - 4 + (40 if 2 + case["delay_days"] <= 3 else 0)
        shortfall = max(0, case["daily_demand"] * 3 - available)
        prediction = shortfall > 0
        rows.append({"id": case["id"], "label_risk": case["label_risk"],
                     "predicted_risk": prediction, "projected_shortfall_units": shortfall})
    tp = sum(r["label_risk"] and r["predicted_risk"] for r in rows)
    fp = sum(not r["label_risk"] and r["predicted_risk"] for r in rows)
    fn = sum(r["label_risk"] and not r["predicted_risk"] for r in rows)
    tn = sum(not r["label_risk"] and not r["predicted_risk"] for r in rows)
    return {"dataset_version": DATASET_VERSION, "synthetic": True, "sample_size": len(rows),
            "method": "deterministic inventory rule", "confusion_matrix": {"tp": tp, "fp": fp, "fn": fn, "tn": tn},
            "detection_recall": tp / (tp + fn) if tp + fn else None,
            "false_positive_rate": fp / (fp + tn) if fp + tn else None,
            "cases": rows,
            "limitations": ["Small synthetic dataset", "No AMD or agent baseline measured", "No latency or forecast error measured"]}


if __name__ == "__main__":
    print(json.dumps(evaluate(), indent=2))
