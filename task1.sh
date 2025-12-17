# 0) 基础设置与工具安装
set -e
OUT=/tmp/acr-scan
mkdir -p "$OUT"

python -m pip install -U pip
python -m pip install -U semgrep bandit ruff

# 如 npm 未安装，优先用 NodeSource 安装（已装可跳过）
if ! command -v npm >/dev/null 2>&1; then
  curl -fsSL https://deb.nodesource.com/setup_20.x | bash -
  apt-get install -y nodejs
fi

# 1) 在 ~/autodl-tmp 下创建示例仓库
BASE=~/autodl-tmp/acr-example
rm -rf "$BASE"
mkdir -p "$BASE/src/py" "$BASE/src/js"

cat > "$BASE/src/py/unsafe.py" <<'PY'
import subprocess, os
def run(cmd):
    # BAD: shell=True
    subprocess.Popen(cmd, shell=True)
def insecure_eval(s):
    return eval(s)
PY

cat > "$BASE/src/js/unsafe.js" <<'JS'
function render(userInput) {
  const div = document.getElementById('app');
  // BAD: innerHTML with unsanitized input
  div.innerHTML = userInput;
  // BAD: eval
  eval("console.log('bad')");
}
JS

# 2) 最小 Semgrep 规则（易命中）
cat > "$BASE/.semgrep.yml" <<'YML'
rules:
  - id: python.subprocess.shell_true
    languages: [python]
    message: "subprocess called with shell=True (command injection risk)"
    severity: ERROR
    pattern: subprocess.Popen(..., shell=True)
  - id: python.eval.use
    languages: [python]
    message: "use of eval() (code injection risk)"
    severity: WARNING
    pattern: eval(...)
  - id: js.innerhtml.unsanitized
    languages: [javascript, typescript]
    message: "unsanitized assignment to innerHTML (XSS risk)"
    severity: ERROR
    pattern: |
      $X.innerHTML = $Y
  - id: js.eval.use
    languages: [javascript, typescript]
    message: "use of eval()"
    severity: WARNING
    pattern: eval(...)
YML

# 3) 初始化 npm + ESLint 最小配置（避免“No configuration found”）
pushd "$BASE" >/dev/null
npm init -y
npm i -D eslint
cat > "$BASE/.eslintrc.json" <<'JSON'
{
  "root": true,
  "extends": ["eslint:recommended"],
  "env": { "browser": true, "node": true, "es2021": true },
  "parserOptions": { "ecmaVersion": 2021 }
}
JSON
popd >/dev/null

# 4) 运行四个扫描并输出 SARIF（注意追加 '|| true'）
pushd "$BASE" >/dev/null

# Semgrep：去掉 --error 或加 || true，避免因“有发现”而退出
semgrep --config .semgrep.yml --sarif --output "$OUT/semgrep.sarif" || true

# Bandit：发现问题时可能非零
bandit -r . -f sarif -o "$OUT/bandit.sarif" || true

# Ruff：有 lint 问题时非零
ruff check . --output-format sarif > "$OUT/ruff.sarif" || true

# ESLint：有问题时非零
npx eslint . -f sarif -o "$OUT/eslint.sarif" || true

popd >/dev/null

# 5) 简单校验
ls -lh "$OUT"