#!/usr/bin/env python3
import argparse, json, os
from pathlib import Path

TOOL_PRIORITY = {"Semgrep": 3, "Bandit": 3, "Ruff": 2, "ESLint": 2, "semgrep":3, "bandit":3, "ruff":2, "eslint":2}
LEVEL_MAP = {"error":"ERROR", "warning":"WARNING", "note":"NOTE", "none":"INFO"}
LEVEL_SCORE = {"ERROR":3, "WARNING":2, "NOTE":1, "INFO":0}

def read_json(p):
    try:
        with open(p, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None

def norm_tool_name(run_name, file_hint):
    if run_name: return run_name
    base = Path(file_hint).stem.lower()
    if "semgrep" in base: return "Semgrep"
    if "bandit" in base: return "Bandit"
    if "ruff" in base: return "Ruff"
    if "eslint" in base: return "ESLint"
    return base

def severity_of(result, tool):
    lvl = result.get("level")
    if isinstance(lvl, str):
        lvl = LEVEL_MAP.get(lvl.lower(), "WARNING")
        return lvl
    # try ESLint/bandit properties
    props = result.get("properties", {})
    sev = props.get("problem.severity") or props.get("security_severity")
    if isinstance(sev, str):
        sev = sev.upper()
        if sev in LEVEL_SCORE: return sev
    return "WARNING"

def rel_path(uri, repo_root):
    if not uri: return ""
    p = Path(uri)
    if p.is_absolute():
        try:
            return str(Path(os.path.relpath(p, repo_root)))
        except Exception:
            return str(p)
    else:
        return str(p)

def load_results(sarif_path, repo_root, counts):
    data = read_json(sarif_path)
    if not data or "runs" not in data: return []
    out = []
    for run in data.get("runs", []):
        tool_name = norm_tool_name(run.get("tool",{}).get("driver",{}).get("name"), sarif_path)
        for res in run.get("results", []) or []:
            counts[tool_name] = counts.get(tool_name, 0) + 1
            rule_id = res.get("ruleId") or (res.get("rule",{}) or {}).get("id") or "unknown-rule"
            msg = (res.get("message") or {}).get("text") or ""
            loc = (res.get("locations") or [{}])[0].get("physicalLocation", {}) or {}
            art = loc.get("artifactLocation", {}) or {}
            uri = art.get("uri") or ""
            region = loc.get("region", {}) or {}
            line = int(region.get("startLine") or 1)
            severity = severity_of(res, tool_name)
            src_file = rel_path(uri, repo_root)
            abs_file = Path(repo_root, src_file) if src_file else None
            snippet = ""
            start = max(1, line - 3); end = line + 3
            if abs_file and abs_file.exists():
                try:
                    lines = abs_file.read_text(encoding="utf-8", errors="ignore").splitlines()
                    total = len(lines)
                    start = max(1, min(start, total))
                    end = max(start, min(end, total))
                    snippet = "\n".join(lines[start-1:end])
                except Exception:
                    snippet = ""
            out.append({
                "source": tool_name,
                "rule_id": rule_id,
                "file": src_file,
                "line": line,
                "severity": severity,
                "message": msg,
                "snippet": snippet,
                "snippet_range": [start, end],
            })
    return out

def rank(item):
    return (TOOL_PRIORITY.get(item["source"], 1), LEVEL_SCORE.get(item["severity"], 0))

def merge_items(items):
    merged = {}
    for it in items:
        key = (it["rule_id"], it["file"], it["line"])
        if key not in merged:
            merged[key] = it
        else:
            if rank(it) > rank(merged[key]):
                merged[key] = it
    return list(merged.values())

def sort_items(items):
    return sorted(items, key=lambda x: (-TOOL_PRIORITY.get(x["source"],1),
                                        -LEVEL_SCORE.get(x["severity"],0),
                                        x["file"], x["line"]))

def write_findings(findings, out_dir):
    p = Path(out_dir, "findings.json")
    p.write_text(json.dumps(findings, indent=2, ensure_ascii=False), encoding="utf-8")

def write_metrics(counts, merged_count, out_dir):
    total = sum(counts.values())
    dedup_rate = 0.0 if total == 0 else round(1 - (merged_count / total), 4)
    payload = {"input_counts": counts, "input_total": total, "merged_count": merged_count, "dedup_rate": dedup_rate}
    Path(out_dir, "agg_metrics.json").write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")

def write_sarif(findings, out_dir):
    run = {"tool":{"driver":{"name":"Merged"}}, "results":[]}
    for f in findings:
        lvl = f["severity"].lower()
        result = {
            "ruleId": f["rule_id"],
            "level": { "error":"error", "warning":"warning", "note":"note", "info":"none" }.get(lvl, "warning"),
            "message": {"text": f["message"]},
            "locations": [{
                "physicalLocation": {
                    "artifactLocation": {"uri": f["file"]},
                    "region": {"startLine": f["line"], "snippet": {"text": f["snippet"]}}
                }
            }]
        }
        run["results"].append(result)
    sarif = {"version":"2.1.0",
             "$schema":"https://schemastore.azurewebsites.net/schemas/json/sarif-2.1.0.json",
             "runs":[run]}
    Path(out_dir, "merged.sarif").write_text(json.dumps(sarif, indent=2, ensure_ascii=False), encoding="utf-8")

def main():
    ap = argparse.ArgumentParser(description="Merge SARIFs, dedupe, add snippets, and sort.")
    ap.add_argument("--in", dest="in_dir", default="/tmp/acr-scan", help="Directory containing sarif files")
    ap.add_argument("--out", dest="out_dir", default="/tmp/acr-findings", help="Output directory")
    ap.add_argument("--repo", dest="repo_root", required=True, help="Repo root for snippet extraction")
    args = ap.parse_args()

    in_dir = Path(args.in_dir); out_dir = Path(args.out_dir); repo_root = Path(args.repo_root)
    out_dir.mkdir(parents=True, exist_ok=True)
    sarifs = [p for p in in_dir.glob("*.sarif")]
    counts = {}
    items = []
    for p in sarifs:
        items.extend(load_results(p, repo_root, counts))
    merged = merge_items(items)
    ordered = sort_items(merged)
    write_findings(ordered, out_dir)
    write_metrics(counts, len(ordered), out_dir)
    write_sarif(ordered, out_dir)
    print(f"Inputs: {sum(counts.values())}, Merged: {len(ordered)}, Out: {out_dir}")

if __name__ == "__main__":
    main()