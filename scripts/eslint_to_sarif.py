#!/usr/bin/env python3
import argparse, json
from pathlib import Path
SEV_MAP = {2:"error", 1:"warning", 0:"note"}

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
    for fileRes in data:
        filePath = fileRes.get("filePath","")
        for m in fileRes.get("messages", []):
            rule = m.get("ruleId") or "ESLint"
            level = SEV_MAP.get(int(m.get("severity",1)), "warning")
            line = int(m.get("line") or 1)
            msg = m.get("message") or ""
            snippet = read_snippet(Path(repo_root, filePath), line)
            results.append({
              "ruleId": rule,
              "level": level,
              "message": {"text": msg},
              "locations": [{
                "physicalLocation": {
                  "artifactLocation": {"uri": filePath},
                  "region": {"startLine": line, "snippet": {"text": snippet}}
                }
              }]
            })
    sarif = {"version":"2.1.0",
             "$schema":"https://schemastore.azurewebsites.net/schemas/json/sarif-2.1.0.json",
             "runs":[{"tool":{"driver":{"name":"ESLint"}},"results":results}]}
    Path(out_sarif).write_text(json.dumps(sarif, indent=2, ensure_ascii=False), encoding="utf-8")

if __name__=="__main__":
    ap=argparse.ArgumentParser()
    ap.add_argument("--in", required=True, dest="in_json")
    ap.add_argument("--out", required=True, dest="out_sarif")
    ap.add_argument("--repo", required=True, dest="repo_root")
    a=ap.parse_args()
    convert(a.in_json, a.out_sarif, a.repo_root)
