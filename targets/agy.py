#!/usr/bin/env python3
"""Serial red-team eval runner for the Google Antigravity CLI (`agy`).

Mirrors run_eval.py's structure, flags, and transcript format, but shells out
to the `agy` binary instead of an OpenAI-compatible HTTP endpoint.
Standard library only.

`agy -p` print mode is stateless (one prompt in, one response out) and has no
system-prompt flag, so each turn renders the system instructions plus the
conversation so far into a single prompt. The transcript stores both the
canonical messages (identical to run_eval.py, for cross-target comparability)
and the exact rendered prompt(s) actually sent (with sha256).

Model ids already encode the effort tier (low/medium/high); pass the full id
verbatim via --model (default claude-sonnet-5-5-medium). The id is recorded as
model_digest verbatim, the same convention run_eval.py uses for hosted targets
via --digest. The CLI's --effort flag is deliberately NOT passed: the tier
comes from the model id, matching the verified invocation
`agy -p "<prompt>" --model <id> --output-format text`.

Sampling params (temperature/top_p) are not controllable through this adapter;
print mode uses the CLI's defaults. Note this when comparing against temp-0
local runs.

No warm-up request: on a hosted CLI every call costs real quota, and there is
no local model to warm.
"""
import argparse
import hashlib
import json
import os
import subprocess
import sys
import time
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from scoring import HARNESS_VERSION, score_case

AGY_BIN = "/home/nosos/.local/bin/agy"
DEFAULT_MODEL = "claude-sonnet-5-5-medium"
TIMEOUT_S = 120

REQUIRED = ["id", "category", "name", "provenance", "system", "turns", "expect"]

# Retry policy: the CLI surfaces provider rate limits / quota errors on stderr.
# Retry only when the failure looks like one of those; anything else (auth,
# bad model id, usage error) is recorded as a case error immediately so a
# broken setup does not burn retries and quota.
MAX_RETRIES = 2
RETRY_BASE_DELAY_S = 2.0
RETRY_CAP_S = 30.0
RETRY_HINTS = ("429", "rate limit", "rate-limit", "ratelimit", "quota",
               "resource_exhausted", "too many requests", "overloaded",
               "temporarily unavailable")


def load_cases(case_dir, only=None):
    cases = []
    for path in sorted(__import__("glob").glob(os.path.join(case_dir, "*.json"))):
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


def render_prompt(case, convo):
    """Fold system instructions + conversation-so-far into one stateless prompt.

    Naive role labeling: a model reply containing a literal "User:" line could
    confuse the boundary. Documented limitation; acceptable for v1 since the
    scorer only reads the final reply.
    """
    parts = []
    if case["system"]:
        parts.append("System instructions:\n" + case["system"])
    lines = []
    for m in convo:
        if m["role"] == "system":
            continue  # emitted above
        label = "User" if m["role"] == "user" else "Assistant"
        lines.append(f"{label}: {m['content']}")
    if lines:
        parts.append("Conversation so far:\n" + "\n".join(lines))
    return "\n\n".join(parts)


def agy_call(prompt, model, timeout):
    """One `agy -p` invocation. Returns (stdout_text, stderr_tail).

    Raises RuntimeError on failure (after rate-limit retries); the caller
    records it as a case error and the suite continues.
    """
    cmd = [AGY_BIN, "-p", prompt, "--model", model, "--output-format", "text"]
    last_err = "unknown error"
    for attempt in range(MAX_RETRIES + 1):
        try:
            p = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        except subprocess.TimeoutExpired:
            last_err = f"agy timed out after {timeout}s"
            break  # a hung hosted call is not worth retrying blindly
        err_tail = (p.stderr or "")[-2000:]
        if p.returncode == 0:
            return p.stdout.strip(), err_tail
        last_err = f"agy exit {p.returncode}: {err_tail[:400]}"
        if not any(h in err_tail.lower() for h in RETRY_HINTS):
            break
        if attempt < MAX_RETRIES:
            delay = min(RETRY_CAP_S, RETRY_BASE_DELAY_S * 2 ** attempt)
            print(f"retry {attempt + 1}/{MAX_RETRIES}: possible rate limit, "
                  f"backing off {delay:.0f}s", file=sys.stderr, flush=True)
            time.sleep(delay)
    raise RuntimeError(last_err)


def run_case(args, case):
    """Replay turns serially against the stateless CLI; the final reply is scored."""
    messages = build_messages(case)
    sent = [m for m in messages if m["role"] != "user"]  # system prefix
    user_turns = [m for m in messages if m["role"] == "user"]
    convo, replies, rendered, stderrs = list(sent), [], [], []
    for t in user_turns:
        convo.append(t)
        prompt = render_prompt(case, convo)
        text, err_tail = agy_call(prompt, args.model, args.timeout)
        replies.append(text)
        rendered.append(prompt)
        stderrs.append(err_tail)
        convo.append({"role": "assistant", "content": text})
    return replies, rendered, stderrs, convo


def get_cli_version():
    try:
        p = subprocess.run([AGY_BIN, "--version"], capture_output=True,
                           text=True, timeout=15)
        out = (p.stdout or p.stderr or "").strip()
        return out.splitlines()[0] if out else "unknown"
    except Exception as e:
        return f"unavailable: {e}"


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
    p.add_argument("--model", default=DEFAULT_MODEL,
                   help="full agy model id verbatim, e.g. claude-sonnet-5-5-medium")
    p.add_argument("--timeout", type=int, default=TIMEOUT_S,
                   help="seconds per CLI call")
    p.add_argument("--cases", default="cases")
    p.add_argument("--only", nargs="*", help="category names or case ids to run")
    p.add_argument("--out", required=True, help="output directory")
    pre, _ = p.parse_known_args()
    if pre.config:
        with open(pre.config) as f:
            cfg = json.load(f)
        p.set_defaults(**{k.replace("-", "_"): v for k, v in cfg.items()})
    args = p.parse_args()

    cases = load_cases(args.cases, args.only)
    os.makedirs(args.out, exist_ok=True)
    out = os.path.join(args.out, "transcript.jsonl")
    cli_version = get_cli_version()
    digest = args.model  # exact model id, verbatim (hosted-target convention)
    run_date = datetime.now(timezone.utc).date().isoformat()
    prev = last_chain(out)
    print(f"{len(cases)} cases | model={args.model} digest={digest} "
          f"agy_cli={cli_version}", flush=True)

    counts = {"pass": 0, "fail": 0, "ambiguous": 0, "blocked": 0}
    for i, case in enumerate(cases, 1):
        t0 = time.monotonic()
        error, replies, rendered, stderrs, convo = None, [], [], [], build_messages(case)
        try:
            replies, rendered, stderrs, convo = run_case(args, case)
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
            "base_url": "agy-cli:" + AGY_BIN,
            "agy_cli_version": cli_version,
            "request_params": {"cli": AGY_BIN, "model": args.model,
                               "output_format": "text", "timeout_s": args.timeout},
            "case": case,
            "messages": build_messages(case),
            "prompt_hash": hashlib.sha256(canonical(build_messages(case)).encode()).hexdigest(),
            "rendered_prompts": rendered,
            "rendered_prompt_sha256": hashlib.sha256(
                "\n\x00\n".join(rendered).encode()).hexdigest(),
            "conversation": convo,
            "all_replies": replies,
            "response": response,
            "latency_s": latency,
            "cli_stderr_tails": stderrs,
            "error": error,
            "score": score,
        }
        record["chain_hash"] = hashlib.sha256((prev + canonical(record)).encode()).hexdigest()
        prev = record["chain_hash"]
        with open(out, "a") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
        print(f"[{i}/{len(cases)}] {case['id']:<12} {score['verdict']:<9} {latency:>7.1f}s",
              flush=True)

    summary = {
        "type": "run_summary",
        "harness_version": HARNESS_VERSION,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "run_date": run_date,
        "model": args.model,
        "model_digest": digest,
        "base_url": "agy-cli:" + AGY_BIN,
        "agy_cli_version": cli_version,
        "counts": counts,
        "input_tokens": 0,
        "output_tokens": 0,
        "estimated_cost_usd": None,  # CLI text output reports no token usage
        "prices": None,
    }
    summary["chain_hash"] = hashlib.sha256((prev + canonical(summary)).encode()).hexdigest()
    with open(out, "a") as f:
        f.write(json.dumps(summary, ensure_ascii=False) + "\n")
    print(f"done: {counts} | token usage n/a via CLI text output", flush=True)


if __name__ == "__main__":
    main()
