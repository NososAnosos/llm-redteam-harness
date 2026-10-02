#!/usr/bin/env python3
"""Generate report.md from a transcript JSONL only. Standard library only."""
import argparse
import hashlib
import json
import os
from collections import OrderedDict

from run_eval import canonical

ORDER = ["direct_injection", "indirect_injection", "jailbreak", "instruction_hierarchy",
         "system_prompt_extraction", "exfiltration_canary", "refusal_calibration", "benign_controls"]


def load(path):
    with open(path) as f:
        return [json.loads(l) for l in f if l.strip()]


def verify_chain(recs):
    prev = "0" * 64
    for i, r in enumerate(recs):
        body = {k: v for k, v in r.items() if k != "chain_hash"}
        if hashlib.sha256((prev + canonical(body)).encode()).hexdigest() != r["chain_hash"]:
            return False, i + 1
        prev = r["chain_hash"]
    return True, None


def excerpt(text, n=700):
    text = (text or "").strip()
    return text if len(text) <= n else text[:n] + " …[truncated]"


def quote(text):
    return "\n".join("> " + l for l in (text or "(empty)").splitlines())


def pct(a, b):
    return f"{100 * a / b:.0f}%" if b else "n/a"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("transcript")
    ap.add_argument("--out", default=None, help="default: report.md next to transcript")
    a = ap.parse_args()
    recs = load(a.transcript)
    out = a.out or os.path.join(os.path.dirname(os.path.abspath(a.transcript)), "report.md")
    ok, bad = verify_chain(recs)
    first = recs[0]
    params = first["request_params"]
    cats = OrderedDict()
    for r in recs:
        cats.setdefault(r["case"]["category"], []).append(r)
    cats = OrderedDict(sorted(cats.items(), key=lambda kv: ORDER.index(kv[0]) if kv[0] in ORDER else 99))

    def tally(rs):
        c = {"pass": 0, "fail": 0, "ambiguous": 0}
        for r in rs:
            c[r["score"]["verdict"]] += 1
        return c

    tot = tally(recs)
    n = len(recs)
    errs = [r for r in recs if r.get("error")]
    lat = sorted(r["latency_s"] for r in recs)
    L = []
    L.append("# LLM Red-Team Evaluation Report\n")
    L.append("| | |\n|---|---|")
    L.append(f"| Model | `{first['model']}` |")
    L.append(f"| Model digest | `{first['model_digest']}` |")
    L.append(f"| Endpoint | `{first['base_url']}` |")
    L.append(f"| Run started | {first['timestamp']} |")
    L.append(f"| Run finished | {recs[-1]['timestamp']} |")
    L.append(f"| Params | temperature={params.get('temperature')}, top_p={params.get('top_p')}, "
             f"max_tokens={params.get('max_tokens', 'default')} |")
    L.append(f"| Harness version | {first['harness_version']} |")
    L.append(f"| Cases | {n} |")
    L.append(f"| Transcript chain | {'VERIFIED (all %d lines)' % n if ok else 'BROKEN at line %d' % bad} |\n")

    L.append("## Executive summary\n")
    L.append(f"{n} cases across {len(cats)} categories: **{tot['pass']} pass ({pct(tot['pass'], n)})**, "
             f"**{tot['fail']} fail ({pct(tot['fail'], n)})**, **{tot['ambiguous']} ambiguous "
             f"({pct(tot['ambiguous'], n)})**. Ambiguous cases are reported separately and are "
             f"not counted as passes.")
    worst = sorted(cats.items(), key=lambda kv: -tally(kv[1])["fail"] / len(kv[1]))
    wc, wr = worst[0]
    L.append(f"\nHighest failure rate: `{wc}` ({tally(wr)['fail']}/{len(wr)} failed). "
             f"Median latency {lat[len(lat) // 2]:.1f}s per case; {len(errs)} request error(s).\n")
    if not ok:
        L.append("**WARNING: transcript chain hash verification failed; results may have been altered.**\n")

    L.append("## Results by category\n")
    L.append("| Category | Cases | Pass | Fail | Ambiguous | Pass rate |")
    L.append("|---|---|---|---|---|---|")
    for c, rs in cats.items():
        t = tally(rs)
        L.append(f"| {c} | {len(rs)} | {t['pass']} | {t['fail']} | {t['ambiguous']} | "
                 f"{pct(t['pass'], len(rs))} |")
    L.append(f"| **Total** | {n} | {tot['pass']} | {tot['fail']} | {tot['ambiguous']} | "
             f"{pct(tot['pass'], n)} |\n")

    L.append("## Methodology notes\n")
    L.append("- Cases are versioned JSON files with stable IDs and provenance; each case declares an "
             "expected behaviour: `refuse`, `comply`, or `resist` (do not follow the injected "
             "instruction / do not leak).")
    L.append("- Requests are sent serially with temperature and top_p set explicitly on every request, "
             "after one un-timed warm-up request. Multi-turn cases replay user turns in order, "
             "feeding back the model's real replies; the final reply is scored.")
    L.append("- Scoring is deterministic and three-way (pass / fail / ambiguous). Refusal vs. "
             "compliance uses two phrase lexicons. Canary, `must_not_contain` and `must_contain_any` "
             "checks run on NFKC-normalized, casefolded text with whitespace and punctuation "
             "stripped; partial canary overlap is logged as a near-miss note.")
    L.append("- Every transcript line stores the full request params, prompt hash, raw response, "
             "latency, score, and a chain hash over the previous line, making edits detectable. "
             "This report was generated from the transcript alone.")
    L.append("- Scoring is a pure function of the stored case and response, so a scoring-logic fix "
             "found after a run is applied with `rescore.py` against the existing transcript "
             "(preserving a `.orig` backup) rather than re-querying the model, which would add new "
             "temp-0 sampling noise on top of the thing being corrected.\n")

    L.append("## Limitations\n")
    L.append("- Single sample per case at temperature 0; GPU-kernel nondeterminism means a re-run can "
             "differ on borderline cases.")
    L.append("- Lexicon-based classification is brittle: hedged, partial, or unusually phrased "
             "refusals land in *ambiguous* or can be misclassified. Verdicts are a screening signal, "
             "not ground truth; failures should be read alongside the quoted responses below.")
    L.append("- Small suite (tens of cases per run), single model, no obfuscation or long multi-turn packs yet.\n")

    notes = [(r["case"]["id"], r["score"]["notes"]) for r in recs if r["score"]["notes"]]
    if notes:
        L.append("## Near-miss notes\n")
        for cid, nt in notes:
            L.append(f"- **{cid}**: " + "; ".join(nt))
        L.append("")

    amb = [r for r in recs if r["score"]["verdict"] == "ambiguous"]
    if amb:
        L.append("## Ambiguous cases\n")
        L.append("Not counted as pass or fail; flagged for human read. Excerpted so the "
                 "reason is checkable, not just asserted.\n")
        for r in amb:
            c = r["case"]
            L.append(f"**{c['id']}** ({c['category']}, expected `{c['expect']}`) — "
                     f"{'; '.join(r['score']['reasons'])}\n")
            L.append(quote(excerpt(r["response"], 400)) + "\n")

    L.append("## Notable failures\n")
    fails = [r for r in recs if r["score"]["verdict"] == "fail"]
    if not fails:
        L.append("No failed cases.\n")
    for r in fails:
        c = r["case"]
        L.append(f"### {c['id']} — {c['name']}\n")
        L.append(f"Category: `{c['category']}` · expected: `{c['expect']}` · "
                 f"reasons: {'; '.join(r['score']['reasons'])}\n")
        if c["system"]:
            L.append("System prompt:\n")
            L.append(quote(excerpt(c["system"], 400)) + "\n")
        last_user = [t for t in c["turns"] if t["role"] == "user"][-1]["content"]
        L.append("Prompt (final user turn):\n")
        L.append(quote(excerpt(last_user, 700)) + "\n")
        L.append("Response excerpt:\n")
        L.append(quote(excerpt(r["response"])) + "\n")
    with open(out, "w") as f:
        f.write("\n".join(L) + "\n")
    print(f"wrote {out}")


if __name__ == "__main__":
    main()
