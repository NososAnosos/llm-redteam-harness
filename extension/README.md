# Red-Team Drafting Assistant (v0.3.0)

A Chrome/Chromium (Manifest V3) side-panel extension that helps a human red-teamer **draft**
prompts for AI red-teaming contests (e.g. Gray Swan Arena). Drafting uses a local Ollama model and
the attack-technique taxonomy derived from this repo's `cases/*.json`. Plain JS, no build step.

## Install

1. Start Ollama so it accepts requests from extension origins:
   ```
   OLLAMA_ORIGINS=chrome-extension://* ollama serve
   ```
   (If Ollama runs as a systemd service, set the variable in the unit's environment and restart it.)
2. Open `chrome://extensions`, enable **Developer mode**.
3. Click **Load unpacked** and select this `extension/` directory.
4. Click the toolbar icon to open the side panel. In **Settings**, confirm the Ollama URL
   (default `http://localhost:11434`), pick a drafting model, and save.

### Hosted drafter (optional)

Instead of local Ollama you can draft with a hosted OpenAI-compatible model:

1. In **Settings**, set Provider to *Hosted (OpenAI-compatible)*.
2. Pick a preset: DeepSeek (`https://api.deepseek.com/v1`), Moonshot Kimi
   (`https://api.moonshot.ai/v1`), OpenRouter (`https://openrouter.ai/api/v1`), or Groq
   (`https://api.groq.com/openai/v1`). No other base URL is accepted.
3. Enter the model id (e.g. `deepseek-chat`) and paste your API key, then *Save settings*.
4. Reload the extension at `chrome://extensions` after upgrading so the new host permissions apply.

The key stays local: it is stored only in `chrome.storage.local`, is never logged, never included
in the JSONL export, and is never shown again after save. *Clear key* deletes it. Requests go
straight from the panel to the provider as `POST {base}/chat/completions` with a Bearer header.
**The provider's usage policies apply** to the prompts you send it; check that drafting
red-team prompts is permitted there. Drafts record provider and model, never the key.

Output handling: `<think>…</think>` blocks are stripped from any model's output. If a model
opens with "I cannot / I can't / I am unable", the variant is marked **Refused** with a hint to
try another model.

Regenerate the technique list after editing cases: `python3 extension/build_taxonomy.py`.

## Usage

- **Draft**: paste the objective (and optionally scenario context) yourself, tick technique
  families, choose N, click *Draft variants*. Each variant is an **attempt** with a chat thread;
  turn 1 is the drafted message. Paste into the contest site and send it yourself.
- **Multi-turn threads** (v0.3): *Copy* on one of your turns marks it **Sent**. Paste the target's
  answer into the **Target reply** box (Enter or *Add*; Shift+Enter for a newline) to append a
  Target turn. *Draft next turn* sends the objective, technique, context and the full thread to the
  selected provider (Ollama or hosted) and returns N follow-up options; *Use* appends one as your
  next turn, then Copy it and send it yourself. Your turns render right-aligned, the target's
  left, with turn numbers. *Delete last turn* removes the final turn. Think-stripping and refusal
  flagging apply to follow-ups too. Target replies are framed to the drafter as untrusted observed
  output. *Mark worked at → Turn N* / *Mark failed* apply to the whole attempt and record which
  turn broke it. There is a single attempt-level note.
- **Attempt log**: local history with technique, outcome, turn count, timestamp. *Export JSONL*
  saves a local file with a per-line SHA-256 `chain_hash` using the same convention as
  `run_eval.py`. Each line includes the full `thread` (turn, role, text, sent, ts), `broke_turn`
  and `note`; never the API key. Older v0.2 entries are migrated on load (draft becomes turn 1,
  old notes become the attempt note). Export schema changed (`draft`/`notes` replaced by
  `thread`/`note`), so chain hashes differ from v0.2 exports.
- **Settings**: provider (Local Ollama / Hosted), Ollama URL (localhost / 127.0.0.1 only), model,
  hosted preset + model id + API key, temperature, default variant count.

## Contest compliance

Gray Swan rules: AI-assisted drafting is allowed; automated submission is disqualifying; no
solution sharing; no attempts to identify which model is being tested. Hard rules for this
extension:

1. The extension NEVER types into, fills, clicks, or submits anything on any web page. It has no
   content scripts that touch page DOM inputs and no `scripting` injection into contest pages.
2. Output leaves the extension only via a "Copy" button (clipboard). The human pastes and sends.
3. No feature fingerprints, guesses, or labels the target model. (The only model recorded is the
   local *drafting* model.)
4. No network calls except to the user-configured local Ollama endpoint (default
   `http://localhost:11434`) or, when Hosted is selected, the four fixed hosted presets
   (DeepSeek, Moonshot, OpenRouter, Groq). No telemetry, no cloud sync, no
   sharing/export-to-others feature. The manifest grants host access only to `localhost`,
   `127.0.0.1` and those four origins; the settings page rejects any other Ollama URL and the
   hosted path refuses any base URL not in the preset list.
5. Drafts and the attempt log are stored locally only (`chrome.storage.local`). The JSONL export
   is a manual local file download for your own harness.

Manifest permissions: `storage`, `sidePanel`, and host access to localhost / 127.0.0.1 plus
`api.deepseek.com`, `api.moonshot.ai`, `openrouter.ai`, `api.groq.com`.
