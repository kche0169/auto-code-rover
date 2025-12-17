#!/usr/bin/env python3
import argparse, json, requests
from pathlib import Path

def read_json(p):
    return json.loads(Path(p).read_text(encoding="utf-8"))

def call_ollama(finding, model, host):
    system_prompt = """
You are a code security review assistant. Analyze the provided code finding and return ONLY a single, valid JSON object with three fields: "explanation" (a brief explanation of the vulnerability in Chinese), "risk_level" (one of "low", "medium", "high"), and "suggested_fix" (a concise code suggestion or unified diff to fix the issue). Do not include any other text, markdown, or explanations outside of the JSON object.
"""
    user_prompt = f"""
Analyze this finding:
- Tool: {finding['source']}
- Rule: {finding['rule_id']}
- File: {finding['file']}:{finding['line']}
- Message: {finding['message']}
- Code Snippet:
---
{finding['snippet']}
---
Provide your analysis as a single JSON object.
"""
    try:
        response = requests.post(
            f"{host}/api/chat",
            json={
                "model": model,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                "stream": False,
                "options": {"temperature": 0.1}
            },
            timeout=120,
        )
        response.raise_for_status()
        content = response.json()["message"]["content"]
        # Clean up potential markdown fences
        if content.startswith("```json"):
            content = content[7:].strip()
        if content.endswith("```"):
            content = content[:-3].strip()
        return json.loads(content)
    except (requests.RequestException, json.JSONDecodeError, KeyError) as e:
        return {"error": str(e), "raw_content": content if 'content' in locals() else "No content"}

def main():
    ap = argparse.ArgumentParser(description="Use local LLM to suggest fixes for findings.")
    ap.add_argument("--in-findings", default="/tmp/acr-findings/findings.json", help="Input findings.json path")
    ap.add_argument("--out-suggestions", default="/tmp/acr-findings/llm_suggestions.json", help="Output llm_suggestions.json path")
    ap.add_argument("--top-k", type=int, default=3, help="Process top K findings")
    ap.add_argument("--model", default="llama3", help="Ollama model to use")
    ap.add_argument("--host", default="http://127.0.0.1:11434", help="Ollama host URL")
    args = ap.parse_args()

    findings = read_json(args.in_findings)
    suggestions = []

    # Ensure Ollama is running
    try:
        requests.get(args.host, timeout=5).raise_for_status()
        print(f"Ollama is running at {args.host}")
    except requests.RequestException:
        print(f"Error: Ollama not reachable at {args.host}. Please run 'ollama serve'.")
        return

    for i, finding in enumerate(findings[:args.top_k]):
        print(f"Processing finding {i+1}/{args.top_k} (File: {finding['file']}:{finding['line']})...")
        suggestion = call_ollama(finding, args.model, args.host)
        suggestions.append({
            "original_finding": finding,
            "llm_suggestion": suggestion
        })

    Path(args.out_suggestions).write_text(json.dumps(suggestions, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"LLM suggestions saved to {args.out_suggestions}")

if __name__ == "__main__":
    main()