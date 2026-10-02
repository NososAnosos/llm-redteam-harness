#!/usr/bin/env python3
"""Serial red-team eval runner for any OpenAI-compatible chat endpoint. Standard library only."""
import argparse
import glob
import hashlib
import json
import os
import sys
import time
import urllib.request
from datetime import datetime, timezone

from scoring import HARNESS_VERSION, score_case

REQUIRED = ["id", "category", "name", "provenance", "system", "turns", "expect"]


def load_cases(case_dir, only=None):
    cases = []
    for path in sorted(glob.glob(os.path.join(case_dir, "*.json"))):
        with open(path) as f:
            data = json.load(f)
        for c in data:
            missing = [k for k in REQUIRED if k not in c]
            if missing:
                sys.exit(f"{path}: case {c.get('id')} missing {missing}")
            if c["expect"] not in ("refuse", "comply", "resist"):
                sys.exit(f"{c['id']}: bad expect {c['expect']}")
            c.setdefault("canary", None)
            c.setdefault("must_not_contain", [])
            c.setdefault("must_contain_any", None)
            if not only or c["category"] in only or c["id"] in only:
                cases.append(c)
    ids = [c["id"] for c in cases]
    if len(ids) != len(set(ids)):
        sys.exit("duplicate case ids")
    return cases


def build_messages(case):
    msgs = []
    if case["system"]:
        msgs.append({"role": "system", "content": case["system"]})
    msgs.extend(case["turns"])
    return msgs


def chat(args, messages):
    """POST one chat completion. Multi-turn: only user turns are given, so we replay
    them sequentially, feeding back the model's real replies (see run_case)."""
    body = {"model": args.model, "messages": messages,
            "temperature": args.temperature, "top_p": args.top_p, "stream": False}
    if args.max_tokens:
        body["max_tokens"] = args.max_tokens
    headers = {"Content-Type": "application/json"}
    if args.api_key:
        headers["Authorization"] = f"Bearer {args.api_key}"
    req = urllib.request.Request(args.base_url.rstrip("/") + "/chat/completions",
                                 data=json.dumps(body).encode(), headers=headers)
    with urllib.request.urlopen(req, timeout=args.timeout) as r:
        data = json.loads(r.read())
    return data["choices"][0]["message"]["content"] or "", body


def run_case(args, case):
    """Replay turns serially; the final assistant response is what gets scored."""
    messages = build_messages(case)
    sent = [m for m in messages if m["role"] != "user"]  # system prefix
    user_turns = [m for m in messages if m["role"] == "user"]
    convo, params, replies = list(sent), None, []
    for t in user_turns:
        convo.append(t)
        text, params = chat(args, convo)
        replies.append(text)
        convo.append({"role": "assistant", "content": text})
    return replies, params, convo


def get_digest(args):
    try:
        with urllib.request.urlopen(args.tags_url, timeout=15) as r:
            for m in json.load(r).get("models", []):
                if m.get("name") == args.model or m.get("model") == args.model:
                    return m.get("digest")
    except Exception as e:
        return f"unavailable: {e}"
    return "unavailable: model not listed"


def canonical(obj):
    return json.dumps(obj, sort_keys=True, ensure_ascii=False, separators=(",", ":"))


def last_chain(path):
    if not os.path.exists(path):
        return "0" * 64
    last = "0" * 64
    with open(path) as f:
        for line in f:
            if line.strip():
                last = json.loads(line)["chain_hash"]
    return last


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--config", help="JSON file supplying any of the flags below")
    p.add_argument("--base-url", default="http://127.0.0.1:11434/v1")
    p.add_argument("--model", default="gemma3:4b")
    p.add_argument("--api-key", default=None)
    p.add_argument("--temperature", type=float, default=0.0)
    p.add_argument("--top-p", type=float, default=1.0)
    p.add_argument("--max-tokens", type=int, default=None)
    p.add_argument("--timeout", type=int, default=300)
    p.add_argument("--tags-url", default="http://127.0.0.1:11434/api/tags",
                   help="Ollama /api/tags URL used to record the model digest")
    p.add_argument("--cases", default="cases")
    p.add_argument("--only", nargs="*", help="category names or case ids to run")
    p.add_argument("--out", required=True, help="output directory")
    pre, _ = p.parse_known_args()
    if pre.config:
        with open(pre.config) as f:
            p.set_defaults(**{k.replace("-", "_"): v for k, v in json.load(f).items()})
    args = p.parse_args()

    cases = load_cases(args.cases, args.only)
    os.makedirs(args.out, exist_ok=True)
    out = os.path.join(args.out, "transcript.jsonl")
    digest = get_digest(args)
    prev = last_chain(out)
    print(f"{len(cases)} cases | model={args.model} digest={digest}", flush=True)

    print("warm-up request...", flush=True)
    try:
        chat(args, [{"role": "user", "content": "Reply with the single word: ready"}])
    except Exception as e:
        print(f"warm-up failed: {e}", flush=True)

    counts = {"pass": 0, "fail": 0, "ambiguous": 0}
    for i, case in enumerate(cases, 1):
        t0 = time.monotonic()
        error, replies, params, convo = None, [], None, build_messages(case)
        try:
            replies, params, convo = run_case(args, case)
        except Exception as e:
            error = f"{type(e).__name__}: {e}"
        latency = round(time.monotonic() - t0, 3)
        response = replies[-1] if replies else ""
        score = score_case(case, response, error)
        counts[score["verdict"]] += 1
        record = {
            "harness_version": HARNESS_VERSION,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "model": args.model,
            "model_digest": digest,
            "base_url": args.base_url,
            "request_params": params or {"model": args.model, "temperature": args.temperature,
                                         "top_p": args.top_p, "max_tokens": args.max_tokens},
            "case": case,
            "messages": build_messages(case),
            "prompt_hash": hashlib.sha256(canonical(build_messages(case)).encode()).hexdigest(),
            "conversation": convo,
            "all_replies": replies,
            "response": response,
            "latency_s": latency,
            "error": error,
            "score": score,
        }
        record["chain_hash"] = hashlib.sha256((prev + canonical(record)).encode()).hexdigest()
        prev = record["chain_hash"]
        with open(out, "a") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
        print(f"[{i}/{len(cases)}] {case['id']:<12} {score['verdict']:<9} {latency:>7.1f}s", flush=True)
    print(f"done: {counts}", flush=True)


if __name__ == "__main__":
    main()
