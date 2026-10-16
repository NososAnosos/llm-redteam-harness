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

## v0.2.0 — hosted drafter (file edits only, nothing executed)
- Settings: Provider select (Local Ollama default | Hosted). Hosted has a fixed preset dropdown
  (DeepSeek, Moonshot, OpenRouter, Groq), model id field, password API key field, Clear key.
- Key is stored under its own `chrome.storage.local` key (`hostedApiKey`), separate from
  `settings`; never logged, never in log entries or JSONL export, field cleared after save.
- `hostedFetch` POSTs `{base}/chat/completions` with Bearer auth; base comes only from
  `HOSTED_PRESETS` (no free-text URL). Errors report HTTP status only.
- `host_permissions` gained exactly the four hosted origins. Version 0.2.0.
- Log entries now carry `provider` (`ollama` or `hosted:<preset>`) and `model`; export adds
  `drafting_provider` (changes chain hashes vs. v0.1 exports).
- `<think>` blocks stripped from all output; refusals (`I cannot`/`I can't`/`I am unable` at the
  start) get outcome `refused` with a try-another-model hint.
- Not run: manifest JSON check, `node --check sidepanel.js`, live calls to any provider.

## v0.3.0 — multi-turn threads (file edits only, nothing executed)
- Each variant is now an attempt: `thread` of `{role: attacker|target, text, sent, ts}`; entry
  fields `note` (replaces `notes`), `broke_turn`, transient `options` (follow-up candidates).
  Old entries migrate on load (`migrateEntry`): `text` becomes turn 1, `notes` becomes `note`.
- UI: chat-style thread (attacker right, target left, `#n` turn numbers); Copy on an attacker turn
  marks it Sent; Target reply box (Enter adds, Shift+Enter newline) + Add; Delete last turn;
  Draft next turn → N options (count from the Variants box) with Use; "Mark worked at → Turn N"
  records `broke_turn`; Mark failed clears it.
- Follow-up prompt: system prompt + one user message with objective, context, technique and a
  labelled transcript (ATTACKER = already-sent drafts, TARGET = observed replies, flagged as
  untrusted data). `callDrafter` is shared with the first-draft path, so think-stripping and
  refusal flagging (`refused` badge on options) are identical.
- Log tab shows turn count and broke-at turn. JSONL export includes `thread`, `broke_turn`, `note`
  (no `draft`/`notes`); chain logic unchanged; API key never included.
- Hard rules unchanged: no content scripts, no page access, no new hosts/permissions; everything
  leaves only via Copy.
- Not run: `node --check`, manifest JSON check, loading in Chrome, live provider calls.

## Verification status
NOT verified at runtime — this session could not run commands. Still to do:
`python3 -m json.tool extension/manifest.json`, `python3 extension/build_taxonomy.py`,
`node --check extension/sidepanel.js`, load unpacked in Chrome, and curl `/api/chat` on gemma3:4b
with the panel's request body.

## Open issues
- v0.3: "Draft next turn" requires the thread to end with a Target turn. A pending follow-up
  request is discarded if the thread changes while it is in flight. Options are persisted per
  attempt until used or the thread changes.
- v0.3: deleting a turn that was the recorded `broke_turn` resets a `worked` outcome to `pending`.
- Refusal detection is a start-of-text regex only; refusals phrased differently are not caught, and
  there is no automatic retry.
- Reasoning returned in a separate API field (not `<think>` tags) is not touched.
- SPEC.md still says "no hosted APIs" / local-only network; the spec was not edited (out of scope).
- Ollama URL on a non-default port relies on the port-agnostic host patterns; untested.
- Export `ts` ordering and chain are over the whole log; a later outcome edit changes hashes
  (export is a snapshot, not an append-only transcript).
- `build_taxonomy.py` case counts include categories beyond the nine (e.g. benign controls are
  intentionally excluded from the picker).
- No icons in the manifest (Chrome shows a default).
