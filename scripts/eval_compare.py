#!/usr/bin/env python3


# python scripts/eval_compare.py \
#   --gold /tmp/eval/gold_findings.json \
#   --preds /tmp/eval/hybrid_findings.json /tmp/eval/tool_findings.json /tmp/eval/llm_findings.json \
#   --metrics /tmp/eval/hybrid_metrics.json /tmp/eval/tool_metrics.json /tmp/eval/llm_metrics.json \
#   --names "Hybrid" "Tool-only" "LLM-only"




import argparse, json
from pathlib import Path
from collections import defaultdict

def load_json(p):
    return json.loads(Path(p).read_text(encoding="utf-8"))

def match_findings(pred, gold, key_fields=("rule_id", "file", "line"), line_tol=1):
    gold_set = set()
    for g in gold:
        gold_set.add((g.get("rule_id"), g.get("file"), int(g.get("line"))))
    tp, fp, fn = 0, 0, 0
    matched = set()
    for p in pred:
        found = False
        for delta in range(-line_tol, line_tol+1):
            key = (p.get("rule_id"), p.get("file"), int(p.get("line"))+delta)
            if key in gold_set:
                found = True
                matched.add(key)
                break
        if found:
            tp += 1
        else:
            fp += 1
    fn = len(gold_set - matched)
    return tp, fp, fn

def print_metrics(name, metrics, tp, fp, fn):
    recall = tp / (tp + fn) if (tp + fn) else 0
    precision = tp / (tp + fp) if (tp + fp) else 0
    print(f"## {name}")
    print(f"- Recall: {recall:.3f}")
    print(f"- Precision: {precision:.3f}")
    for k, v in metrics.items():
        print(f"- {k}: {v}")
    print()

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--gold", required=True, help="Ground truth findings.json")
    ap.add_argument("--preds", nargs="+", required=True, help="List of findings.json to compare")
    ap.add_argument("--metrics", nargs="+", required=True, help="List of metrics.json (same order as preds)")
    ap.add_argument("--names", nargs="+", required=True, help="Names for each method")
    args = ap.parse_args()

    gold = load_json(args.gold)
    for pred_path, metrics_path, name in zip(args.preds, args.metrics, args.names):
        pred = load_json(pred_path)
        metrics = load_json(metrics_path)
        tp, fp, fn = match_findings(pred, gold)
        print_metrics(name, metrics, tp, fp, fn)

if __name__ == "__main__":
    main()