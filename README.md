# AutoCodeRover: Local Context-Aware Code Review Pipeline

## Overview

AutoCodeRover is a local, context-aware code review agent that runs a full loop of "Discovery → Evidence → Noise Reduction & Ranking → LLM Explanation/Suggestion → Controlled Fix → Verification → Metrics". The pipeline is fully local, using static analysis tools and a local LLM (Ollama/llama3) for explainability and suggestions. All steps are CLI-driven and can be demoed or integrated into CI.

---

## Pipeline Tasks

### Task 1: Discovery & Evidence (Generate SARIF)

**What:**  
Scan the target codebase with multiple static analysis/quality tools (Semgrep, Bandit, Ruff, ESLint) and output unified SARIF evidence (rule ID, file, line, message, severity).

**Input:**  
- Target code repository (should be a git repo, with minimal config: `.semgrep.yml` in root; `.eslintrc.json` or `eslint.config.cjs` for JS/TS).

**How:**  
- Activate your conda environment and install the tools.
- Run each tool in the repo root to generate SARIF files.

**Commands:**
```bash
# Install tools (if not already)
python -m pip install -U pip semgrep bandit ruff

# ESLint setup (inside repo root)
npm init -y
npm i -D eslint
cat > eslint.config.cjs <<'CJS'
module.exports = [
  {
    files: ["**/*.js"],
    languageOptions: { ecmaVersion: 2021, sourceType: "module" },
    rules: { "no-eval": "warn" }
  }
];
CJS

# Run scans (replace <REPO> with your repo path)
semgrep --config .semgrep.yml --sarif --output /tmp/acr-scan/semgrep.sarif || true
bandit -r <REPO> -f json -o /tmp/acr-scan/bandit.json || true
ruff check <REPO> --output-format sarif > /tmp/acr-scan/ruff.sarif || true
npx eslint <REPO> -f json -o /tmp/acr-scan/eslint.json || true
```

**Success Criteria:**  
- `/tmp/acr-scan/semgrep.sarif`, `bandit.json`, `ruff.sarif`, `eslint.json` all exist and contain valid SARIF or JSON with `runs/results` or equivalent.

---

### Task 2: Noise Reduction & Ranking (Aggregate Findings)

**What:**  
Merge, deduplicate, and enrich SARIF results from all tools, attach code snippets, and sort findings by tool priority and severity.

**Input:**  
- The four SARIF/JSON files from Task 1.

**How:**  
- Convert Bandit and ESLint JSON to SARIF:
```bash
python scripts/bandit_to_sarif.py --in /tmp/acr-scan/bandit.json --out /tmp/acr-scan/bandit.sarif --repo <REPO>
python scripts/eslint_to_sarif.py --in /tmp/acr-scan/eslint.json --out /tmp/acr-scan/eslint.sarif --repo <REPO>
```
- Merge all SARIFs:
```bash
python scripts/merge_sarif.py --in /tmp/acr-scan --out /tmp/acr-findings --repo <REPO>
```

**Success Criteria:**  
- `/tmp/acr-findings/findings.json` contains a non-empty, structured list of findings.
- `/tmp/acr-findings/agg_metrics.json` shows input/merged counts and deduplication rate.
- `/tmp/acr-findings/merged.sarif` is a valid SARIF file.

---

### Task 3: LLM Explanation & Suggestion (Read-Only, Local LLM)

**What:**  
For the Top-K findings, use local llama3 (via Ollama) to generate a brief explanation, risk assessment, and minimal fix suggestion.

**Input:**  
- `findings.json` (with code snippets).

**How:**  
- Ensure Ollama is running:
```bash
ollama serve &
```
- Run the suggestion script:
```bash
python scripts/llm_suggest.py --in-findings /tmp/acr-findings/findings.json --out-suggestions /tmp/acr-findings/llm_suggestions.json --top-k 3
```

**Success Criteria:**  
- `/tmp/acr-findings/llm_suggestions.json` contains structured explanations and suggestions for Top-K findings (fields: explanation, risk_level, suggested_fix).

---

### Task 4: Controlled Fix, Verification & Metrics

**What:**  
Generate a read-only reproduction script (`repro.sh`), a fix plan (`patches.json`), re-scan after (simulated) fixes, and output metrics.

**Input:**  
- `findings.json`, `llm_suggestions.json`, and the target repo.

**How:**  
```bash
python scripts/gen_repro_and_metrics.py --findings /tmp/acr-findings/findings.json --llm /tmp/acr-findings/llm_suggestions.json --repo <REPO> --outdir /tmp/acr-findings
```

**Success Criteria:**  
- `/tmp/acr-findings/repro.sh`: a script listing all fix plans and re-scan commands.
- `/tmp/acr-findings/patches.json`: structured fix plans.
- `/tmp/acr-findings/semgrep_post.sarif`: SARIF after (simulated) fixes.
- `/tmp/acr-findings/metrics.json`: metrics including pre/post finding counts, LLM coverage, and reduction.

---

## Common Pitfalls & Tips

- **No scan results:** Use rules that are easy to trigger (e.g., `eval`, `innerHTML`, `shell=True`).
- **ESLint config errors:** Ensure `.eslintrc.json` or `eslint.config.cjs` exists in repo root.
- **LLM output not structured:** Shorten code snippets, lower Top-K, and enforce strict JSON output in prompts.
- **Patch application fails:** Always check with `git apply --check`; skip if not cleanly applicable.
- **No tests:** Use "pre/post scan difference" as the main verification metric.

---

## Demo Workflow

1. Run all four tasks in sequence using the commands above.
2. All outputs are in `/tmp/acr-findings/` and `/tmp/acr-scan/`.
3. Use `metrics.json` and `semgrep_post.sarif` to demonstrate the effect.

---

## Example Output Directory

```
/tmp/acr-findings/
├── agg_metrics.json
├── findings.json
├── llm_suggestions.json
├── merged.sarif
├── metrics.json
├── patches.json
├── repro.sh
├── semgrep_post.sarif
```

---

## License

MIT
