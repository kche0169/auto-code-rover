#!/usr/bin/env python3
import argparse, json
from pathlib import Path
SEV_MAP = {"HIGH":"error","MEDIUM":"warning","LOW":"note"}

def read_snippet(fp, line, pad=3):
    try:
        lines = Path(fp).read_text(encoding="utf-8", errors="ignore").splitlines()
        s = max(1, line-pad); e = min(len(lines), line+pad)
        return "\n".join(lines[s-1:e])
    except Exception:
        return ""

def convert(in_json, out_sarif, repo_root):
    data = json.loads(Path(in_json).read_text(encoding="utf-8"))
    results=[]
    for it in data.get("results", []):
        filename = it.get("filename","")
        line = int(it.get("line_number") or 1)
        level = SEV_MAP.get(str(it.get("issue_severity","")).upper(), "warning")
        rule = it.get("test_id") or "Bandit"
        msg = it.get("issue_text") or ""
        snippet = read_snippet(Path(repo_root, filename), line)
        results.append({
          "ruleId": rule,
          "level": level,
          "message": {"text": msg},
          "locations": [{
            "physicalLocation": {
              "artifactLocation": {"uri": filename},
              "region": {"startLine": line, "snippet": {"text": snippet}}
            }
          }]
        })
    sarif = {"version":"2.1.0",
             "$schema":"https://schemastore.azurewebsites.net/schemas/json/sarif-2.1.0.json",
             "runs":[{"tool":{"driver":{"name":"Bandit"}},"results":results}]}
    Path(out_sarif).write_text(json.dumps(sarif, indent=2, ensure_ascii=False), encoding="utf-8")

if __name__=="__main__":
    ap=argparse.ArgumentParser()
    ap.add_argument("--in", required=True, dest="in_json")
    ap.add_argument("--out", required=True, dest="out_sarif")
    ap.add_argument("--repo", required=True, dest="repo_root")
    a=ap.parse_args()
    convert(a.in_json, a.out_sarif, a.repo_root)
