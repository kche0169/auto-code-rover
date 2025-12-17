#!/usr/bin/env python3
import json, argparse, subprocess
from pathlib import Path

def load_json(p):
    return json.loads(Path(p).read_text(encoding="utf-8"))

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--findings", default="/tmp/acr-findings/findings.json")
    ap.add_argument("--llm", default="/tmp/acr-findings/llm_suggestions.json")
    ap.add_argument("--repo", default="~/autodl-tmp/acr-example")
    ap.add_argument("--outdir", default="/tmp/acr-findings")
    ap.add_argument("--semgrep", default="semgrep")
    args = ap.parse_args()
    repo = Path(args.repo).expanduser()
    outdir = Path(args.outdir)
    outdir.mkdir(parents=True, exist_ok=True)

    findings = load_json(args.findings)
    llm = load_json(args.llm)
    patches = []
    repro_lines = [
        "#!/bin/bash",
        f"cd {repo.resolve()}",
        "# 1. Tool auto-fix commands (not executed in read-only mode)",
        "# ruff --fix .",
        "# npx eslint . --fix",
        "",
        "# 2. LLM suggested fixes (only show diff and check in read-only mode)"
    ]
    for i, item in enumerate(llm):
        f = item["original_finding"]
        sug = item.get("llm_suggestion", {})
        fix = sug.get("suggested_fix") or ""
        if fix and "diff" in fix:
            # unified diff
            diff_file = outdir / f"llm_patch_{i+1}.diff"
            diff_file.write_text(fix, encoding="utf-8")
            repro_lines.append(f"# LLM suggested patch {i+1}:")
            repro_lines.append(f"cat > {diff_file} <<'EOF'\n{fix}\nEOF")
            repro_lines.append(f"git apply --check {diff_file} || echo 'patch {i+1} cannot be applied directly'")
        elif fix:
            repro_lines.append(f"# LLM suggested fix {i+1}: {fix}")
        else:
            repro_lines.append(f"# LLM suggested fix {i+1}: No structured suggestion")
        patches.append({
            "finding": f,
            "llm_suggestion": sug,
            "plan": fix
        })
    repro_lines += [
        "",
        "# 3. Re-scan (read-only mode)",
        f"{args.semgrep} --config .semgrep.yml --sarif --output {outdir}/semgrep_post.sarif || true"
    ]
    (outdir / "repro.sh").write_text("\n".join(repro_lines), encoding="utf-8")
    (outdir / "patches.json").write_text(json.dumps(patches, indent=2, ensure_ascii=False), encoding="utf-8")

    # 4. Auto re-scan
    try:
        subprocess.run([
            args.semgrep, "--config", str(repo / ".semgrep.yml"),
            "--sarif", "--output", str(outdir / "semgrep_post.sarif")
        ], cwd=repo, check=False)
    except Exception as e:
        print("semgrep re-scan failed:", e)

    # 5. Metrics
    pre = len(findings)
    post = 0
    try:
        sarif = load_json(outdir / "semgrep_post.sarif")
        post = sum(len(run.get("results", [])) for run in sarif.get("runs", []))
    except Exception:
        pass
    metrics = {
        "pre_findings": pre,
        "llm_suggestions": len(llm),
        "post_findings": post,
        "llm_structured": sum(1 for x in llm if "explanation" in x.get("llm_suggestion", {})),
        "llm_parse_error": sum(1 for x in llm if "error" in x.get("llm_suggestion", {})),
        "reduction": pre - post
    }
    (outdir / "metrics.json").write_text(json.dumps(metrics, indent=2, ensure_ascii=False), encoding="utf-8")
    print("Task 4 finished. Outputs: repro.sh, patches.json, semgrep_post.sarif, metrics.json")

if __name__ == "__main__":
    main()