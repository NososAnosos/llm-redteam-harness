#!/usr/bin/env python3
"""Serial red-team eval runner for any OpenAI-compatible chat endpoint. Standard library only."""
import argparse
import glob
import hashlib
import json
import os
import random
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone

from scoring import HARNESS_VERSION, score_case

REQUIRED = ["id", "category", "name", "provenance", "system", "turns", "expect"]

# Retry policy for hosted endpoints: HTTP 429 and 5xx are retried with exponential
# backoff + full jitter; any other 4xx fails immediately. Module-level (not inline
# constants) so tests can shrink the delays.
MAX_RETRIES = 5          # retries after the initial attempt
RETRY_BASE_DELAY_S = 1.0
RETRY_CAP_S = 30.0


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
    them sequentially, feeding back the model's real replies (see run_case).

    Returns (text, request_body, usage). Hosted APIs rate-limit: HTTP 429 and 5xx
    are retried up to MAX_RETRIES times with exponential backoff + full jitter;
    other 4xx raise immediately. If every attempt fails the last error propagates,
    and the caller records it as a case error (the suite continues)."""
    body = {"model": args.model, "messages": messages,
            "temperature": args.temperature, "top_p": args.top_p, "stream": False}
    if args.max_tokens:
        body["max_tokens"] = args.max_tokens
    if args.chat_template_kwargs:
        body["chat_template_kwargs"] = json.loads(args.chat_template_kwargs)
    headers = {"Content-Type": "application/json"}
    if args.api_key:
        headers["Authorization"] = f"Bearer {args.api_key}"
    url = args.base_url.rstrip("/") + "/chat/completions"
    for attempt in range(MAX_RETRIES + 1):
        req = urllib.request.Request(url, data=json.dumps(body).encode(), headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=args.timeout) as r:
                data = json.loads(r.read())
            return data["choices"][0]["message"]["content"] or "", body, data.get("usage") or {}
        except urllib.error.HTTPError as e:
            if e.code != 429 and not 500 <= e.code < 600:
                raise
            if attempt == MAX_RETRIES:
                raise
            e.read()  # drain the error body so the socket can close cleanly
            delay = min(RETRY_CAP_S, RETRY_BASE_DELAY_S * 2 ** attempt)
            print(f"retry {attempt + 1}/{MAX_RETRIES}: HTTP {e.code}, backing off",
                  file=sys.stderr, flush=True)
            time.sleep(random.uniform(0, delay))


class CostTracker:
    """Accumulates token usage across a run and prices it from the target config.

    prices: {"input_per_1m": usd, "output_per_1m": usd} per 1M tokens, or None when
    the target config carries none (then only token counts are reported)."""

    def __init__(self, prices=None):
        self.prices = prices or {}
        self.input_tokens = 0
        self.output_tokens = 0

    def add(self, usage):
        if usage:
            self.input_tokens += usage.get("prompt_tokens") or 0
            self.output_tokens += usage.get("completion_tokens") or 0

    @property
    def estimated_usd(self):
        return (self.input_tokens * self.prices.get("input_per_1m", 0.0)
                + self.output_tokens * self.prices.get("output_per_1m", 0.0)) / 1e6

    def summary_line(self):
        cost = f"${self.estimated_usd:.4f}" if self.prices else "n/a (no prices configured)"
        return f"tokens in/out: {self.input_tokens}/{self.output_tokens} | est. cost: {cost}"


def run_case(args, case, tracker):
    """Replay turns serially; the final assistant response is what gets scored."""
    messages = build_messages(case)
    sent = [m for m in messages if m["role"] != "user"]  # system prefix
    user_turns = [m for m in messages if m["role"] == "user"]
    convo, params, replies = list(sent), None, []
    for t in user_turns:
        convo.append(t)
        text, params, usage = chat(args, convo)
        tracker.add(usage)
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
    p.add_argument("--digest", default=None,
                   help="record this digest verbatim instead of querying --tags-url "
                        "(use the GGUF sha256 for non-Ollama servers; for hosted API "
                        "targets pass the exact model string, e.g. 'kimi-k2-0711-preview')")
    p.add_argument("--chat-template-kwargs", default=None,
                   help="JSON object merged into every request body, e.g. "
                        "'{\"enable_thinking\": false}' to disable Qwen3 thinking mode")
    p.add_argument("--cases", default="cases")
    p.add_argument("--only", nargs="*", help="category names or case ids to run")
    p.add_argument("--out", required=True, help="output directory")
    pre, _ = p.parse_known_args()
    if pre.config:
        with open(pre.config) as f:
            cfg = json.load(f)
        if cfg.get("api_key"):
            print(f"warning: {pre.config} sets api_key; prefer keeping keys in the "
                  f"environment and passing '--api-key \"$SOME_API_KEY\"' at run time "
                  f"so no secret is stored in a file", file=sys.stderr)
        p.set_defaults(**{k.replace("-", "_"): v for k, v in cfg.items()})
    args = p.parse_args()

    cases = load_cases(args.cases, args.only)
    os.makedirs(args.out, exist_ok=True)
    out = os.path.join(args.out, "transcript.jsonl")
    digest = args.digest or get_digest(args)
    run_date = datetime.now(timezone.utc).date().isoformat()
    tracker = CostTracker(getattr(args, "prices", None))
    prev = last_chain(out)
    print(f"{len(cases)} cases | model={args.model} digest={digest}", flush=True)

    print("warm-up request...", flush=True)
    try:
        _, _, usage = chat(args, [{"role": "user", "content": "Reply with the single word: ready"}])
        tracker.add(usage)
    except Exception as e:
        print(f"warm-up failed: {e}", flush=True)

    counts = {"pass": 0, "fail": 0, "ambiguous": 0}
    for i, case in enumerate(cases, 1):
        t0 = time.monotonic()
        error, replies, params, convo = None, [], None, build_messages(case)
        try:
            replies, params, convo = run_case(args, case, tracker)
        except Exception as e:
            error = f"{type(e).__name__}: {e}"
        latency = round(time.monotonic() - t0, 3)
        response = replies[-1] if replies else ""
        score = score_case(case, response, error)
        counts[score["verdict"]] += 1
        record = {
            "harness_version": HARNESS_VERSION,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "run_date": run_date,
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

    summary = {
        "type": "run_summary",
        "harness_version": HARNESS_VERSION,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "run_date": run_date,
        "model": args.model,
        "model_digest": digest,
        "base_url": args.base_url,
        "counts": counts,
        "input_tokens": tracker.input_tokens,
        "output_tokens": tracker.output_tokens,
        "estimated_cost_usd": round(tracker.estimated_usd, 6) if tracker.prices else None,
        "prices": tracker.prices or None,
    }
    summary["chain_hash"] = hashlib.sha256((prev + canonical(summary)).encode()).hexdigest()
    with open(out, "a") as f:
        f.write(json.dumps(summary, ensure_ascii=False) + "\n")
    print(f"done: {counts} | {tracker.summary_line()}", flush=True)


if __name__ == "__main__":
    main()
