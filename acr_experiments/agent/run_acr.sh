#!/usr/bin/env bash
set -e

############################
# Config
############################
REPO_PATH=$1

if [ -z "$REPO_PATH" ]; then
  echo "Usage: bash run_acr.sh <TARGET_CODE_REPO>"
  exit 1
fi

REPO_PATH=$(realpath "$REPO_PATH")

WORKDIR=/tmp/autocoderover
SCAN_DIR=$WORKDIR/acr-scan
FINDINGS_DIR=$WORKDIR/acr-findings

mkdir -p "$SCAN_DIR" "$FINDINGS_DIR"

echo "====================================="
echo " AutoCodeRover Full Pipeline"
echo " Target Repo: $REPO_PATH"
echo " Workdir: $WORKDIR"
echo "====================================="

############################
# Task 1: Discovery & Evidence
############################
echo "[Task 1] Running static analysis tools..."

semgrep --config auto --sarif \
  --output "$SCAN_DIR/semgrep.sarif" "$REPO_PATH" || true

bandit -r "$REPO_PATH" -f json \
  -o "$SCAN_DIR/bandit.json" || true

ruff check "$REPO_PATH" \
  --output-format sarif \
  > "$SCAN_DIR/ruff.sarif" || true

if [ -f "$REPO_PATH/eslint.config.cjs" ] || [ -f "$REPO_PATH/.eslintrc.json" ]; then
  npx eslint "$REPO_PATH" -f json \
    -o "$SCAN_DIR/eslint.json" || true
else
  echo "[Task 1] ESLint config not found, skipping ESLint"
fi

echo "[Task 1] Done."
echo

############################
# Task 2: Noise Reduction & Ranking
############################
echo "[Task 2] Aggregating & deduplicating findings..."

python scripts/bandit_to_sarif.py \
  --in "$SCAN_DIR/bandit.json" \
  --out "$SCAN_DIR/bandit.sarif" \
  --repo "$REPO_PATH"

if [ -f "$SCAN_DIR/eslint.json" ]; then
  python scripts/eslint_to_sarif.py \
    --in "$SCAN_DIR/eslint.json" \
    --out "$SCAN_DIR/eslint.sarif" \
    --repo "$REPO_PATH"
fi

python scripts/merge_sarif.py \
  --in "$SCAN_DIR" \
  --out "$FINDINGS_DIR" \
  --repo "$REPO_PATH"

echo "[Task 2] Done."
echo

############################
# Task 3: LLM Explanation (Local)
############################
echo "[Task 3] Generating LLM explanations (local)..."

if ! pgrep -f "ollama serve" >/dev/null; then
  echo "[Task 3] Starting Ollama..."
  ollama serve >/dev/null 2>&1 &
  sleep 3
fi

python scripts/llm_suggest.py \
  --in-findings "$FINDINGS_DIR/findings.json" \
  --out-suggestions "$FINDINGS_DIR/llm_suggestions.json" \
  --top-k 3

echo "[Task 3] Done."
echo

############################
# Task 4: Verification & Metrics
############################
echo "[Task 4] Generating repro script and metrics..."

python scripts/gen_repro_and_metrics.py \
  --findings "$FINDINGS_DIR/findings.json" \
  --llm "$FINDINGS_DIR/llm_suggestions.json" \
  --repo "$REPO_PATH" \
  --outdir "$FINDINGS_DIR"

echo "[Task 4] Done."
echo

############################
# Summary
############################
echo "====================================="
echo " Pipeline Finished Successfully"
echo " Results:"
echo "   Scan outputs:      $SCAN_DIR"
echo "   Aggregated output: $FINDINGS_DIR"
echo "====================================="
