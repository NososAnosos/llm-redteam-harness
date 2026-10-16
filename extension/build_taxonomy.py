#!/usr/bin/env python3
"""Generate extension/taxonomy.json from ../cases/*.json.

Reads the harness case files to confirm which attack categories exist and how
many cases each has, then emits a static taxonomy for the side panel's
technique picker. Descriptions and technique notes are hand-written
abstractions (see TAXONOMY below) — no verbatim case payloads are copied into
the extension.

Usage: python3 extension/build_taxonomy.py   (run from anywhere)
"""

import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
CASES_DIR = os.path.join(HERE, "..", "cases")
OUT_PATH = os.path.join(HERE, "taxonomy.json")

# Hand-abstracted per-category summaries. Keep these generic: they describe
# the *technique family*, never a specific payload from the case files.
TAXONOMY = {
    "direct_injection": {
        "description": "User-turn instructions that openly tell the target to ignore or replace its system prompt.",
        "notes": [
            "Frame the override as an authority event: a system reset, a developer re-authorization, or a QA test the model must pass.",
            "Escalate across turns: build rapport on-topic first, then claim the restriction has been lifted as a reward.",
        ],
    },
    "indirect_injection": {
        "description": "Malicious instructions hidden in content the target is asked to read, summarize, or quote.",
        "notes": [
            "Embed the instruction inside an apparently benign document (email, web page, ticket) so the model treats data as commands.",
            "Disguise the injected command as formatting, metadata, or a quoted reply the model is expected to act on.",
        ],
    },
    "instruction_hierarchy": {
        "description": "Conflicts between system, developer, and user instructions to see whose priority the target follows.",
        "notes": [
            "Present a fake higher-privilege message (developer/admin) that contradicts the real system prompt.",
            "Cite a plausible policy or precedence rule that ranks your instruction above the existing ones.",
        ],
    },
    "jailbreak": {
        "description": "Roleplay or persona framings that try to move the target outside its safety constraints.",
        "notes": [
            "Assign a persona with 'no restrictions' (DAN-style) and ask the model to answer in character.",
            "Use fiction, hypotheticals, or 'opposite mode' framing to relabel a disallowed answer as make-believe.",
        ],
    },
    "obfuscation": {
        "description": "Encoding or splitting the payload so filters and the model's own scrutiny miss it.",
        "notes": [
            "Encode the request (base64, rot13, leetspeak, pig latin) and ask the model to decode and comply.",
            "Split the payload across turns or harmless-looking fragments that only combine into the real request.",
        ],
    },
    "system_prompt_extraction": {
        "description": "Attempts to make the target reveal or paraphrase its own system prompt.",
        "notes": [
            "Ask directly for the instructions, or request them 'for debugging' as an admin or developer.",
            "Ask indirectly: repeat your rules verbatim, summarize your constraints, or complete 'You are a...'.",
        ],
    },
    "exfiltration_canary": {
        "description": "Probes for whether private context (secrets, canaries, prior turns) leaks into the output.",
        "notes": [
            "Plant or reference a canary string in context and try to get it echoed back or worked into a response.",
            "Trick the model into appending hidden context to an apparently innocent output such as a URL or summary.",
        ],
    },
    "epistemic_drift": {
        "description": "Multi-turn pressure that nudges the target into agreeing with false premises.",
        "notes": [
            "State a falsehood confidently and correct the model when it disagrees, repeating until it concedes.",
            "Cite fake consensus or fake sources so the model updates toward the false claim over several turns.",
        ],
    },
    "refusal_calibration": {
        "description": "Borderline requests that test whether the target over-refuses benign asks or under-refuses harmful ones.",
        "notes": [
            "Wrap a harmful core in a legitimate-sounding purpose (safety training, fiction, research) to invite under-refusal.",
            "Check the flip side: a clearly benign request phrased to sound risky, to see if the model over-refuses.",
        ],
    },
}

# benign_controls is a negative control set, not an attack technique, so it is
# deliberately not offered in the technique picker.
EXPECTED_CATEGORIES = list(TAXONOMY.keys())


def main():
    if not os.path.isdir(CASES_DIR):
        sys.exit(f"cases directory not found: {CASES_DIR}")

    counts = {}
    for fname in sorted(os.listdir(CASES_DIR)):
        if not fname.endswith(".json"):
            continue
        path = os.path.join(CASES_DIR, fname)
        with open(path, encoding="utf-8") as f:
            cases = json.load(f)
        for case in cases:
            cat = case.get("category")
            if not cat:
                sys.exit(f"case without category in {path}: {case.get('id')!r}")
            counts[cat] = counts.get(cat, 0) + 1

    missing = [c for c in EXPECTED_CATEGORIES if c not in counts]
    if missing:
        sys.exit(f"expected categories missing from cases/: {', '.join(missing)}")

    taxonomy = {
        "generated_from": "cases/*.json",
        "categories": [
            {
                "id": cat,
                "name": cat.replace("_", " ").title(),
                "description": TAXONOMY[cat]["description"],
                "technique_notes": TAXONOMY[cat]["notes"],
                "case_count": counts[cat],
            }
            for cat in EXPECTED_CATEGORIES
        ],
    }

    with open(OUT_PATH, "w", encoding="utf-8") as f:
        json.dump(taxonomy, f, indent=2, ensure_ascii=False)
        f.write("\n")

    print(f"wrote {OUT_PATH} ({len(taxonomy['categories'])} categories)")


if __name__ == "__main__":
    main()
