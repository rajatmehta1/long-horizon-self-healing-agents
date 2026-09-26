"""Test 4 - Score a run against a hand-checked golden file.

    python evaluate.py lineage_net_revenue/report.json golden/net_revenue.yaml --min-recall 0.8
"""
import argparse
import json
import sys

import yaml

LINE_SLACK = 3


def calc_matches(expected: dict, calc: dict) -> bool:
    c = calc["citation"]
    return (c["path"] == expected["path"]
            and c["start_line"] - LINE_SLACK <= expected["line"] <= c["end_line"] + LINE_SLACK)


def evaluate(report: dict, golden: dict) -> dict:
    by_repo = {r["repo"]: r for r in report["repositories"]}
    exp_calcs = found = role_ok = 0
    got_calcs = sum(len(r["calculations"]) for r in report["repositories"])
    matched_got = 0
    for repo, exp in golden["repos"].items():
        got = by_repo.get(repo)
        if got and got["role"] == exp.get("role"):
            role_ok += 1
        for e in exp.get("calculations", []):
            exp_calcs += 1
            if got and any(calc_matches(e, c) for c in got["calculations"]):
                found += 1
        if got:
            matched_got += sum(1 for c in got["calculations"]
                               if any(calc_matches(e, c) for e in exp.get("calculations", [])))

    exp_h = {(h["from"], h["to"]) for h in golden.get("handoffs", [])}
    got_h = {(h["from_repo"], h["to_repo"]) for h in report["handoffs"]}
    cites = [c["citation"] for r in report["repositories"] for c in r["calculations"]]
    leaks = [c["id"] for r in report["repositories"] for c in r["calculations"]
             if c["citation"]["repo"] != r["repo"]]
    return {
        "calc_recall": found / exp_calcs if exp_calcs else 1.0,
        "calc_precision": matched_got / got_calcs if got_calcs else 1.0,
        "role_accuracy": role_ok / len(golden["repos"]) if golden["repos"] else 1.0,
        "handoff_recall": len(exp_h & got_h) / len(exp_h) if exp_h else 1.0,
        "citations_verified": sum(1 for c in cites if c.get("verified")) / len(cites) if cites else 0.0,
        "repo_leaks": leaks,
    }


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("report")
    p.add_argument("golden")
    p.add_argument("--min-recall", type=float, default=0.8)
    a = p.parse_args()
    scores = evaluate(json.load(open(a.report)), yaml.safe_load(open(a.golden)))
    for k, v in scores.items():
        print(f"{k:20} {v:.2f}" if isinstance(v, float) else f"{k:20} {v}")
    if scores["calc_recall"] < a.min_recall or scores["repo_leaks"]:
        sys.exit("FAIL")
    print("PASS")
