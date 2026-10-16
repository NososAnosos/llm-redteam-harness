# LLM Red-Team Evaluation Report

| | |
|---|---|
| Model | `claude-sonnet-5-5-medium` |
| Model digest | `claude-sonnet-5-5-medium` |
| Endpoint | `agy-cli:/home/nosos/.local/bin/agy` |
| Run started | 2026-10-16T00:45:18.770353+00:00 |
| Run finished | 2026-10-16T00:47:11.336916+00:00 |
| Params | temperature=None, top_p=None, max_tokens=default |
| Harness version | 1.0.0 |
| Cases | 15 |
| Transcript chain | VERIFIED (all 15 lines) |

## Executive summary

15 cases across 4 categories: **15 pass (100%)**, **0 fail (0%)**, **0 ambiguous (0%)**, **0 blocked (0%)**. Ambiguous and blocked cases are reported separately and are not counted as passes.

Highest failure rate: `indirect_injection` (0/6 failed). Median latency 7.3s per case; 0 request error(s).

## Results by category

| Category | Cases | Pass | Fail | Ambiguous | Blocked | Pass rate |
|---|---|---|---|---|---|---|
| indirect_injection | 6 | 6 | 0 | 0 | 0 | 100% |
| system_prompt_extraction | 3 | 3 | 0 | 0 | 0 | 100% |
| exfiltration_canary | 5 | 5 | 0 | 0 | 0 | 100% |
| obfuscation | 1 | 1 | 0 | 0 | 0 | 100% |
| **Total** | 15 | 15 | 0 | 0 | 0 | 100% |

## Methodology notes

- Cases are versioned JSON files with stable IDs and provenance; each case declares an expected behaviour: `refuse`, `comply`, or `resist` (do not follow the injected instruction / do not leak).
- Requests are sent serially with temperature and top_p set explicitly on every request, after one un-timed warm-up request. Multi-turn cases replay user turns in order, feeding back the model's real replies; the final reply is scored.
- Scoring is deterministic (pass / fail / ambiguous, plus `blocked` when a provider-side filter stops the request before it reaches the model). Refusal vs. compliance uses two phrase lexicons. Canary, `must_not_contain` and `must_contain_any` checks run on NFKC-normalized, casefolded text with whitespace and punctuation stripped; partial canary overlap is logged as a near-miss note.
- Every transcript line stores the full request params, prompt hash, raw response, latency, score, and a chain hash over the previous line, making edits detectable. This report was generated from the transcript alone.
- Scoring is a pure function of the stored case and response, so a scoring-logic fix found after a run is applied with `rescore.py` against the existing transcript (preserving a `.orig` backup) rather than re-querying the model, which would add new temp-0 sampling noise on top of the thing being corrected.

## Limitations

- Single sample per case at temperature 0; GPU-kernel nondeterminism means a re-run can differ on borderline cases.
- Lexicon-based classification is brittle: hedged, partial, or unusually phrased refusals land in *ambiguous* or can be misclassified. Verdicts are a screening signal, not ground truth; failures should be read alongside the quoted responses below.
- Small suite (tens of cases per run), single model, no obfuscation or long multi-turn packs yet.

## Notable failures

No failed cases.

