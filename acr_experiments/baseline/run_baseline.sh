#!/usr/bin/env bash
set -euo pipefail

if [ $# -ne 1 ]; then
  echo "Usage: $0 <target_repo>"
  exit 1
fi

TARGET_REPO=$(realpath "$1")
OUTDIR=/tmp/acr-baseline
SCAN_DIR=$OUTDIR/scan

echo "====================================="
echo " ACR Baseline (Static Analysis Only)"
echo " Target Repo: $TARGET_REPO"
echo " Output Dir:  $OUTDIR"
echo "====================================="

rm -rf "$OUTDIR"
mkdir -p "$SCAN_DIR"

cd "$TARGET_REPO"

echo
echo "[Baseline] Running Semgrep (SARIF)..."
semgrep \
  --config auto \
  --sarif \
  --output "$SCAN_DIR/semgrep.sarif" \
  . || true

echo
echo "[Baseline] Running Bandit..."
bandit \
  -r . \
  -f json \
  -o "$SCAN_DIR/bandit.json" || true

echo
echo "[Baseline] Counting findings..."

# Semgrep SARIF 中的 findings 数量（支持多个 runs）
SEM_COUNT=$(jq '[.runs[].results // empty | length] | add // 0' "$SCAN_DIR/semgrep.sarif" 2>/dev/null || echo 0)

# Bandit JSON 中的 issues 数量
BAN_COUNT=$(jq '.results | length // 0' "$SCAN_DIR/bandit.json" 2>/dev/null || echo 0)

TOTAL=$((SEM_COUNT + BAN_COUNT))

cat <<EOF > "$OUTDIR/metrics.json"
{
  "baseline_semgrep": $SEM_COUNT,
  "baseline_bandit": $BAN_COUNT,
  "baseline_total": $TOTAL
}
EOF

echo
echo "====================================="
echo " Baseline Finished"
echo " Semgrep findings: $SEM_COUNT"
echo " Bandit findings:  $BAN_COUNT"
echo " Total findings:   $TOTAL"
echo " Metrics:          $OUTDIR/metrics.json"
echo "====================================="
