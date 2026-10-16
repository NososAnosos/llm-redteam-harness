# Build notes — Red-Team Drafting Assistant v0

## Built by Kimi (ran out of quota mid-task)
- `manifest.json`, `background.js` (opens side panel on action click), `sidepanel.html/css/js`,
  `build_taxonomy.py`, generated `taxonomy.json` (9 categories, abstracted notes, case counts).
- Draft flow via Ollama `/api/chat`, attempt log, JSONL export with SHA-256 chain matching
  `run_eval.py` (`canonical()` + `sha256(prev + canonical(record))`, prev starts at 64 zeros).

## Finished/reviewed by Claude (file edits only, nothing executed)
- Reviewed all files against SPEC.md; element IDs between HTML and JS match; chain-hash logic
  matches `run_eval.py`.
- Removed `optional_host_permissions` (`http(s)://*/*`). `host_permissions` now only
  `http://localhost/*` and `http://127.0.0.1/*` (any port).
- Removed the runtime `chrome.permissions.request` path for arbitrary origins; added
  `isLocalOllamaUrl()` check in Settings save and in every Ollama fetch.
- Fixed: auto-selected model in the dropdown was never persisted, so Draft said "pick a model".
- Fixed: temperature now clamped to 0–2 (0 was previously reset to default).
- Wrote `README.md` (install, `OLLAMA_ORIGINS=chrome-extension://*`, Contest compliance) and this file.

## Verification status
NOT verified at runtime — this session could not run commands. Still to do:
`python3 -m json.tool extension/manifest.json`, `python3 extension/build_taxonomy.py`,
`node --check extension/sidepanel.js`, load unpacked in Chrome, and curl `/api/chat` on gemma3:4b
with the panel's request body.

## Open issues
- Thinking models (e.g. qwen3) may return reasoning text in the draft; no `think:false` handling.
- Models may refuse to draft; there is no retry or refusal detection.
- Ollama URL on a non-default port relies on the port-agnostic host patterns; untested.
- Export `ts` ordering and chain are over the whole log; a later outcome edit changes hashes
  (export is a snapshot, not an append-only transcript).
- `build_taxonomy.py` case counts include categories beyond the nine (e.g. benign controls are
  intentionally excluded from the picker).
- No icons in the manifest (Chrome shows a default).
