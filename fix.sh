# 1) Fix ESLint config and generate JSON
pushd ~/autodl-tmp/acr-example
rm -f eslint.config.js # Remove old config

# Create correct CommonJS config file (eslint.config.cjs)
cat > eslint.config.cjs <<'CJS'
module.exports = [
  {
    files: ["**/*.js"],
    languageOptions: {
      ecmaVersion: 2021,
      sourceType: "module",
      globals: {
        browser: true,
        node: true,
        es2021: true
      }
    },
    rules: {
      "no-eval": "warn"
    }
  }
];
CJS

# Run ESLint and output JSON
npx eslint . -f json -o /tmp/acr-scan/eslint.json || true
popd

# 2) Generate Bandit JSON (already successful)
bandit -r ~/autodl-tmp/acr-example -f json -o /tmp/acr-scan/bandit.json || true

# 3) Create conversion scripts
# scripts/bandit_to_sarif.py
cat > scripts/bandit_to_sarif.py <<'PY'
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
PY

# scripts/eslint_to_sarif.py
cat > scripts/eslint_to_sarif.py <<'PY'
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
PY

# 4) Run conversion
python scripts/bandit_to_sarif.py --in /tmp/acr-scan/bandit.json --out /tmp/acr-scan/bandit.sarif --repo ~/autodl-tmp/acr-example
python scripts/eslint_to_sarif.py --in /tmp/acr-scan/eslint.json --out /tmp/acr-scan/eslint.sarif --repo ~/autodl-tmp/acr-example

# 5) Run merge
python scripts/merge_sarif.py --in /tmp/acr-scan --out /tmp/acr-findings --repo ~/autodl-tmp/acr-example

# 6) Check final results
ls -lh /tmp/acr-findings
cat /tmp/acr-findings/agg_metrics.json