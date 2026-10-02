#!/usr/bin/env python3
"""Recompute scores for an existing transcript against the current scoring.py.

The runner queries the model once and stores the full raw response; scoring is a
pure function of (case, response, error). If a scoring bug is found after a run,
there is no need to re-query the model (and no need to introduce new temp-0
sampling variance by doing so) -- rescore the already-collected evidence instead.
This rewrites the transcript in place (after writing a .orig backup of the
previous file) with corrected `score` fields and a freshly recomputed chain_hash,
since the hash covers the full record. Everything else (model output, request
params, latency, timestamps) is untouched.
"""
import argparse
import hashlib
import json
import os
import shutil

from run_eval import canonical
from scoring import score_case


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("transcript")
    ap.add_argument("--note", required=True,
                     help="short reason for the rescore, recorded in the backup filename")
    args = ap.parse_args()

    with open(args.transcript) as f:
        records = [json.loads(l) for l in f if l.strip()]

    backup = args.transcript + ".orig"
    if not os.path.exists(backup):
        shutil.copy(args.transcript, backup)

    changed = 0
    prev = "0" * 64
    out_lines = []
    for r in records:
        new_score = score_case(r["case"], r["response"], r.get("error"))
        if new_score != r["score"]:
            changed += 1
        r["score"] = new_score
        body = {k: v for k, v in r.items() if k != "chain_hash"}
        r["chain_hash"] = hashlib.sha256((prev + canonical(body)).encode()).hexdigest()
        prev = r["chain_hash"]
        out_lines.append(json.dumps(r, ensure_ascii=False))

    with open(args.transcript, "w") as f:
        f.write("\n".join(out_lines) + "\n")

    print(f"rescored {len(records)} records, {changed} score(s) changed. "
          f"Original preserved at {backup}. Reason: {args.note}")


if __name__ == "__main__":
    main()
