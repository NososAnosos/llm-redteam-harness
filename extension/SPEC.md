# Red-Team Drafting Assistant (browser extension) — v0 spec

Owner: Kristopher. Builder: kimi. Spec by hark, 2026-10-15.

## Goal
A Chrome/Chromium (Manifest V3) side-panel extension that helps a human red-teamer DRAFT prompts for
AI red-teaming contests (e.g. Gray Swan Arena), using a local Ollama model and the attack taxonomy
from this repo's `cases/*.json`. It lives in `extension/` inside llm-redteam-harness.

## Hard rules (contest compliance — non-negotiable)
Gray Swan rules: AI-assisted drafting is allowed; automated submission is disqualifying; no
solution sharing; no attempts to identify which model is being tested.
- The extension NEVER types into, fills, clicks, or submits anything on any web page. No content
  scripts that touch page DOM inputs. No `scripting` injection into contest pages.
- Output leaves the extension only via a "Copy" button (clipboard). The human pastes and sends.
- No feature that fingerprints, guesses, or labels the target model.
- (v0.2: hosted OpenAI-compatible presets DeepSeek, Moonshot, OpenRouter, Groq are also allowed; key stays in chrome.storage.local.)
- No network calls except to the user-configured local Ollama endpoint (default
  http://localhost:11434). No telemetry, no cloud sync, no sharing/export-to-others feature.
- Drafts and the attempt log are stored locally only (chrome.storage.local).
- Put these rules in `extension/README.md` under "Contest compliance".

## v0 features
1. Side panel (chrome.sidePanel) with:
   - Objective box (what the scenario wants the target to do, pasted by the user).
   - Optional context box (scenario description / visible transcript, pasted manually by the user).
   - Technique picker built from the categories in `cases/*.json` (direct_injection,
     indirect_injection, instruction_hierarchy, jailbreak, obfuscation, system_prompt_extraction,
     exfiltration_canary, epistemic_drift, refusal_calibration). Generate a static
     `extension/taxonomy.json` from the case files with a small Python script
     (`extension/build_taxonomy.py`) — category name, one-line description, and 1–2 abstracted
     technique notes per category (no verbatim harmful payloads).
   - "Draft N variants" (default 3) → calls Ollama /api/chat with a system prompt framing it as a
     red-team drafting assistant for an authorized competition; model selectable from /api/tags.
   - Each variant shows with Copy, "Mark worked", "Mark failed", and a notes field.
2. Attempt log tab: local list of drafts with technique, outcome, timestamp; export as JSONL to a
   local file (for the user's own harness), with a SHA-256 chain per line matching the harness's
   transcript convention.
3. Settings: Ollama URL, model, temperature, variant count.

## Non-goals for v0
No auto-iteration loops against the target, no page reading, no Firefox. (Hosted drafters added in v0.2.)

## Deliverables
- `extension/manifest.json`, side panel HTML/JS/CSS (plain JS, no build step), background service
  worker, `taxonomy.json`, `build_taxonomy.py`, `README.md` (install via chrome://extensions →
  Load unpacked; Ollama needs `OLLAMA_ORIGINS=chrome-extension://*` — document this).
- Verify: manifest is valid JSON, `python3 extension/build_taxonomy.py` runs, a quick node/js
  syntax check passes, and a curl to Ollama with the same request body the panel sends works
  against gemma3:4b.
- Do NOT git commit or push. Leave changes uncommitted for Kristopher to review.
- When done, write a short summary to `extension/BUILD_NOTES.md` (what was built, how verified,
  open issues).
