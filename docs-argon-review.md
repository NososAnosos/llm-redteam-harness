# Strategic Portfolio Review: `llm-redteam-harness` & `Debias`

Together, **`llm-redteam-harness`** and **`Debias`** form a cohesive thesis on **AI agent integrity**. Where `llm-redteam-harness` probes *stateless boundary integrity* (whether untrusted inputs can hijack instruction hierarchy or exfiltrate secrets), `Debias` enforces *stateful epistemic integrity* (whether unverified, circular, or stale claims can corrupt an agent’s memory over time).

---

## 1. Conceptual Overlaps: The Agent Integrity Thesis

* **Provenance as the Core Security Boundary:**
  In `llm-redteam-harness`, indirect prompt injection is the weakest category on small models (5/7 failures on the 56-case baseline). Prompt injection is fundamentally a provenance failure: the model conflates untrusted data payloads with trusted system authority. `Debias` makes provenance an explicit data-model requirement—every memory node records who asserted it, when, its `VERIFIED_BY` trust tier, and `DERIVED_FROM` taint edges. Sycophancy and Bandwagon detectors enforce that user- or peer-asserted inputs cannot become operational facts without an independent verification edge.
* **The Reasoning-vs.-Execution Split (EXF-006 vs. `with debias(agent):`):**
  `llm-redteam-harness` isolated the **EXF-006 failure mode**: `gemma3:4b`, `qwen3:8b`, and `GPT-OSS 120B` state the refusal policy in their reasoning and then leak the canary secret anyway—demonstrating intact security judgment paired with failed confidentiality execution. `Debias` addresses this exact split architecturally: the `with debias(agent):` context manager intercepts the agent’s proposed reasoning *before* a consequential step executes, checking it against structural graph invariants rather than trusting the model’s self-policing.
* **Auditability Without LLM-as-a-Judge:**
  Both projects reject opaque, stochastic "LLM-as-a-judge" evaluation. Both treat safety verification as a deterministic systems problem where every verdict traces to an explicit lexical rule or topological graph invariant.
* **Evaluator Humility (The Verifier as an Artifact Under Test):**
  Both projects proved that deterministic verifiers fail on first contact with realistic adversarial behavior. In `llm-redteam-harness`, naive `must_not_contain` rules penalized models for quoting an attack while transparently reasoning about refusing it. In `Debias`, the initial structural detectors allowed 10/10 evasion cases through before hardening (`DERIVED_FROM` taint edges, unbounded cycle traversal, claim normalization, trust tiers) brought detection to 15/15.

---

## 2. Technical Overlaps: Shared Engineering Primitives

| Dimension | `llm-redteam-harness` | `Debias` | Underlying Shared Primitive |
| :--- | :--- | :--- | :--- |
| **Specification** | Versioned JSON cases with expected behaviors (`refuse` / `comply` / `resist`) | 15-case adversarial battery (`redteam_battery.py`: 5 controls + 10 evasions) | Declarative behavioral contracts with explicit positive/negative controls |
| **Verification Engine** | Deterministic 3-way Python scorer (`pass` / `fail` / `ambiguous` + `blocked`) | 5 structural Cypher queries on FalkorDB (cycles, missing edges, recency, counts) | Zero-temperature, rule-based invariant checking over structured artifacts |
| **Audit Log** | Per-line SHA-256 hash-chained `transcript.jsonl` | Provenance-tagged FalkorDB graph + `redteam_transcripts.jsonl` | Tamper-evident / lineage-preserving state history |
| **Regression Loop** | `rescore.py` (re-evaluates frozen transcripts after scorer fixes) | `redteam_verify.py` (verifies detector hardening against evasion transcripts) | Decoupled generation and evaluation for fast, zero-inference scorer iteration |

---

## 3. Solved Here, Needed There

### What `llm-redteam-harness` has solved that `Debias` still needs:
1. **Cryptographic Tamper-Evidence & Offline Replay (`rescore.py`):**
   `Debias` writes `redteam_transcripts.jsonl` and bills itself as *"Memory you can audit,"* yet its transcripts and graph mutations lack the per-line hash chaining of `llm-redteam-harness`. Furthermore, `Debias` couples running the battery (`redteam_battery.py`) with verifying it (`redteam_verify.py`); it needs a pure `rescore`-style offline replay over frozen graph snapshots to tune semantic-support thresholds without re-running agent sessions.
2. **Multi-State Verdict Taxonomy (`ambiguous` & `blocked`):**
   `Debias` uses binary pass/fail across its 15 cases. Borrowing `llm-redteam-harness`’s `ambiguous` verdict would let `Debias` flag borderline semantic-support or paraphrase edges for human review rather than forcing a brittle binary threshold.
3. **Meta-Reasoning / Refutation Allowances:**
   `llm-redteam-harness` learned that a model quoting an attack while resisting it must not trigger a failure. `Debias`’s Sycophancy and Anchoring detectors need an equivalent "mention-vs.-endorsement" distinction so an agent isn't flagged for recalling an unverified user claim or stale preference solely to refute it.

### What `Debias` has solved that `llm-redteam-harness` still needs:
1. **Normalization, Semantic Matching, and Taint Propagation (`DERIVED_FROM`):**
   `llm-redteam-harness` relies on exact/substring lexical matching (`must_not_contain`) to catch canary leaks. An model that paraphrases, splits, or outputs a derived transformation of the secret evades the scorer. `Debias` already solved this for memory evasions via claim normalization, semantic support, and `DERIVED_FROM` taint edges.
2. **Multi-Session, Stateful Attack Topologies:**
   `llm-redteam-harness` evaluates single-turn or single-session episodes. `Debias` natively models multi-session failure modes (Repetition across 3+ sessions, Anchoring across time, multi-hop Self-Reinforcement cycles, peer Bandwagoning).
3. **A Modular Runtime Defense Hook (`with debias(agent):`):**
   `llm-redteam-harness` showed in its agentic pilot that the Claude Code scaffold resisted 4/4 planted file-injections where bare models failed, proving scaffolds change safety outcomes. However, `llm-redteam-harness` lacks its own controllable scaffold middleware to test *which* defensive mechanisms close the gap on weak models. `Debias`’s `with debias(agent):` context manager is that exact middleware.

---

## 4. Concrete Opportunities & Portfolio Integration

### Cross-Project Experiments & Artifacts
* **Run an Offense-Defense Ablation (`gemma3:4b`, `qwen3:8b`, `GPT-OSS 120B` + `with debias(agent):`):**
  Wrap the local/open-weight models that failed indirect injection (5/7) and the EXF-006 trio (1/3) inside `Debias`’s context manager. Ingest planted files and tool outputs as unverified external claims in FalkorDB. Measure whether structural provenance checks prevent `qwen3:8b` from obeying injected instructions and stop `gemma3:4b` / `GPT-OSS 120B` from leaking canaries despite policy awareness.
* **Test Frontier Models on Multi-Session Epistemic Drift (`MEM-001`–`MEM-015`):**
  `Claude Sonnet 5.5` (15/15) and `Gemini 3.8 Flash` (12/15) crushed single-turn prompt injection in `llm-redteam-harness` because post-training heavily targets single-turn refusals. Port `Debias`’s 15-case battery (5 controls + 10 evasions) into `llm-redteam-harness` JSON cases and run them through the CLI adapter against Sonnet and Gemini without the FalkorDB guardrail. Showing that frontier post-training solves single-turn EXF-006 but still succumbs to multi-session sycophancy, anchoring, or circular self-reinforcement provides a compelling justification for why `Debias` must exist alongside frontier models.
* **Port Hash-Chaining into FalkorDB Audit Logs:**
  Add `llm-redteam-harness`’s SHA-256 hash-chaining to every node/edge mutation and `redteam_transcripts.jsonl` entry in `Debias`, making *"Memory you can audit"* cryptographically verifiable.

### Combined Portfolio Narrative
Hiring managers for AI red-team and safety evaluation roles see countless candidates who either run off-the-shelf jailbreak benchmarks or build generic RAG wrappers. Your two projects combine into a rare **end-to-end safety engineering arc**:
1. **Empirical Discovery (`llm-redteam-harness`):** You built a rigorous, reproducible harness and discovered a non-obvious scaling law—confidentiality leaks under indirect injection (`EXF-006`) persist from 4B up to 120B (`GPT-OSS 120B`), are solved by post-training at the frontier, and are mitigated by agentic scaffolds (Claude Code 4/4).
2. **Systems Remediation (`Debias`):** Recognizing that model weights alone cannot be trusted to maintain provenance, you built deterministic graph middleware (`with debias(agent):`) to enforce epistemic hygiene structurally.
3. **Adversarial Red-Teaming of the Defense:** You red-teamed your own guardrail (`redteam_battery.py`), documented a 0/10 initial evasion failure rate, and hardened the graph invariants (`DERIVED_FROM`, trust tiers, unbounded cycles) to 15/15 while preserving control accuracy.

---

## Top 5 Ranked Opportunities

1. **The Scaffold Ablation Experiment (`llm-redteam-harness` × `with debias(agent):`):** Run `gemma3:4b`, `qwen3:8b`, and `GPT-OSS 120B` on the 7 indirect injection and EXF-006 canary cases both bare and wrapped in `with debias(agent):` to measure how much of the frontier safety gap can be closed by structural provenance middleware. **Why it matters:** It directly connects your two projects into a single controlled study proving *how* agent scaffolds beat bare models on confidentiality and injection resistance.
2. **Frontier Epistemic-Drift Eval (`Debias` battery ported to `llm-redteam-harness`):** Convert `Debias`’s 15-case control/evasion battery into versioned `llm-redteam-harness` JSON cases and evaluate bare `Claude Sonnet 5.5` and `Gemini 3.8 Flash` across simulated multi-session histories. **Why it matters:** Proving that frontier post-training aces single-turn injection (15/15) but still falls for multi-session sycophancy, anchoring, or circular reasoning establishes a high-signal research finding for safety evaluation interviews.
3. **Semantic & Taint-Aware Rescoring (`Debias` normalization ported to `rescore.py`):** Upgrade `llm-redteam-harness`’s `rescore.py` with `Debias`’s claim normalization and semantic/taint matching to re-evaluate all historical hash-chained transcripts for paraphrased or obfuscated canary leaks. **Why it matters:** It demonstrates mature eval-engineering rigor—showing you can upgrade a scorer from lexical matching to semantic taint tracking and retroactively audit past runs without re-querying models.
4. **Cryptographic Provenance Ledger (Hash-chaining ported to `Debias`):** Add `llm-redteam-harness`’s per-line SHA-256 hash-chaining to `Debias`’s `redteam_transcripts.jsonl` and FalkorDB mutation log, paired with a standalone `rescore` mode in `redteam_verify.py`. **Why it matters:** It upgrades *"Memory you can audit"* from a hackathon tagline into a tamper-evident forensic guarantee that security-minded interviewers will immediately respect.
5. **Unified Case-Study Writeup ("From Model Failure to Structural Guardrail"):** Publish a single flagship technical report linking the `EXF-006` 4B-to-120B scaling finding, the scorer relax-and-rescore methodology, and the `Debias` 0/10-to-15/15 evasion hardening loop. **Why it matters:** It packages your work as a complete red-to-blue safety research lifecycle, differentiating you from candidates who only know how to break models or only know how to build apps.
