# STATUS — Privacy Pass for Hermes

**As of:** November 6, 2026 (evening, KST)
**Headline:** Engineering is complete and published. The plugin is live at
[github.com/jgarr16/privacy-pass](https://github.com/jgarr16/privacy-pass)
(catalog pin `c2ccc60f505590e8e7a10b519e438be3aa61b90f`), and the *published*
artifact — not just the checkout — has passed the end-to-end egress gate.
What remains is submission mechanics: catalog PR, demo video, X post, Typeform.
**Deadline:** November 11, 5:00 p.m. EST / November 12, 7:00 a.m. KST (from the
hackathon announcement; organizer confirmation still pending).

---

## 1. Where we are relative to the plan

The original plan (README §8) ran Nov 5–11 with submission on Nov 10–11. Work
actually started Nov 6 (one day slip); the calendar was re-baselined the same
day and the scope-control rule applied (desktop panel, extra detectors, local
bypass cut). We are now **ahead of the re-baselined plan by roughly four days**:

| Re-baselined plan | Planned for | Actual |
|---|---|---|
| Day-one gate (fake SSN absent from effective request) | Nov 6 | **Nov 6** — at middleware-contract level, then proven **live end-to-end** same day |
| `llm_request` hardening + registry + restoration | Nov 7 | **Nov 6** — verified from installed Hermes source; hook return-shape bug found and fixed |
| Tool request policy + guard + result sanitization | Nov 8 | **Nov 6** — full layer built and tested |
| Fail-closed edges, audit, settings, `/privacy` | Nov 9 | **Nov 6** — config schema, counts-only audit, persistence |
| Integration tests, clean-checkout packaging, docs | Nov 10 | **Nov 6** — 62 tests, docs package, clean-clone rehearsal |
| Demo capture, public repo, catalog PR, submit | Nov 11 | **Repo published Nov 6**; PR/demo/submit remain |

Remaining work is user-gated and mechanical (~2 hours total): no code is
required to reach a complete submission.

---

## 2. What has been built

Six commits, 62 tests, all verification gates green.

| Commit | Content |
|---|---|
| `9587a3c` | Day one: vendored core (`privacy_pass/`) with additive session-alias support in `sanitize()`; new `registry.py` (stable session aliases, idempotent re-sanitization), `policy.py` (dates/generalization off by default), `engine.py` (per-session state, counts-only audit); native plugin at repo root (`llm_request` middleware, `transform_llm_output` hook, `/privacy` command, sidecar bootstrap); day-one egress gate tests |
| `81ab864` | `transform_llm_output` contract verified from installed Hermes source (payload key `response_text`, plain-string return); fixed hook that would have been silently ignored; recorded Hermes' persist-and-replay behavior and API-error dump redaction |
| `7939bf2` | **Live egress gate passed end-to-end** via offline mock provider + sandboxed `HERMES_HOME`; root-caused the stale-gateway staleness trap; structured-only policy for system messages (NER was aliasing every tool name in Hermes' system prompt); auxiliary-call accounting via `pre_auxiliary_call` |
| `42109d0` | Tool-call protection (`tool_request` middleware, `pre_tool_call` block guard, `transform_tool_result` with destination-based policy); session persistence (0600 files, `HERMES_HOME`-aware, purge); `config_schema` (protect_list / skip_list / mode); docs package (`SECURITY.md`, `KNOWN_LIMITS.md`, `DEMO.md`, `SUBMISSION.md`); CI workflow; catalog entry draft |
| `c2ccc60` | `scripts/demo_gate.sh` (one-command offline rehearsal, idempotent, stale-gateway-safe); default skip terms ("SSN" no longer NER-aliased); five-turn stability + tool-call-args tests; **dependency license review closed** (spaCy, presidio-analyzer, en_core_web_sm — all MIT); clean-checkout rehearsal passed |
| `536221c` | Catalog SHA pinned; demo config-order warning (overwriting `config.yaml` after `plugins enable` silently disables the plugin — caught during published-artifact verification) |

### Verification evidence

- **62/62 tests**, including the day-one gate: synthetic SSN/name/email absent
  from the serialized effective provider payload; aliases stable across turns;
  malformed requests fail closed; tool args/results sanitized; persistence
  restart-continuity; file permissions.
- **`hermes plugins doctor`** — OK (4 hooks, 2 middleware).
- **`hermes plugins validate --install-deps`** — the catalog admission check —
  passes (manifest, loadability, capability match, security scan, no core
  override).
- **Live gate (offline, real Hermes):** one-shot Hermes turn against a local
  mock provider through a sandboxed Hermes home — main provider request
  contains aliases only (zero raw values), system prompt untouched by NER,
  reply fully restored with no alias tokens, session store written with 0600
  permissions.
- **Clean-checkout rehearsal:** fresh `git clone` → `validate --install-deps`
  → `hermes plugins install <git-url>` → enable → `doctor` → demo gate PASS,
  twice consecutively.
- **Published-artifact verification:** `hermes plugins install
  jgarr16/privacy-pass` from GitHub into a fresh Hermes home — same gate,
  PASS. (First attempt leaked; root cause was the test harness overwriting
  `config.yaml` after enabling, wiping the `plugins.enabled` record. Harness
  mistake, documented as a warning in `docs/DEMO.md`.)

### Key engineering discoveries (all documented in README §4 and docs/)

1. Hermes middleware is **fail-open by design** — fail-closed is implemented
   inside our handler (blocked request with no conversation content).
2. Presidio **deliberately rejects canonical placeholder SSNs**
   (`123-45-6789`); tests/demos use plausible synthetic values.
3. hermes-agent pins `numpy==2.5.4` vs presidio's `<2.5` cap — resolved via
   the documented **sidecar runtime** (`python_runtime: external`).
4. **Auxiliary LLM calls (titling, compaction, vision) are observer-only
   surfaces** — no plugin can sanitize them; confirmed from source and live
   capture. We count them and disclose in `/privacy`; mitigation:
   `auxiliary.title_generation.enabled: false`.
5. A running gateway daemon keeps plugin modules in memory — restart it after
   plugin changes (cost one debug cycle; documented).

---

## 3. Milestone scorecard (README §8)

**Milestone A — Repository and core: COMPLETE.** Core extracted and vendored;
existing tests inherited and passing; session registry, policy module,
synthetic fixtures added; adapter-facing API implemented
(`sanitize_request`, `sanitize_tool_args`, `restore_response` via the engine).

**Milestone B — Native Hermes plugin: COMPLETE.** Valid `plugin.yaml` +
`register(ctx)`; `llm_request` middleware covering both `messages` and
Responses `input` forms; `tool_request` middleware; `transform_tool_result`
and `transform_llm_output` (hold_stream) hooks; `pre_tool_call` guard;
status command with audit counts; **tested on fresh Hermes profiles with no
local-path dependencies** (clean clone and GitHub install).

**Milestone C — Quality and submission: ~90%.** Outbound payload capture with
fake identifiers: done. Multi-turn, streaming (held-stream split across
chunks), malformed data, overlapping detectors, restart, parallel sessions:
done (in tests or the live gate). Unsupported routes block or warn accurately:
done (attachment passthrough disclosed; auxiliary calls counted and
disclosed). Docs (threat model, limits, modes, data deletion): done.
**Remaining:** demo video recording, catalog PR, X post, Typeform — all
mechanical, all prepared.

### Plan items consciously not built (by design)

- Work/Strict modes (`mode` config key exists; v1 implements Personal only —
  as planned).
- `pre_llm_call` / `post_api_request` P1 hooks (superseded: `pre_auxiliary_call`
  gives better observability for the actual gap; `llm_request` middleware is
  the egress guard, as the README always specified).
- Desktop panel (P2) — cut per scope-control rule.
- `sessions.py`/`server.py`/`web.py` from the original repo — intentionally
  not ported (`sessions.py` stored raw originals to disk; our store is
  registry snapshots with restricted permissions; server/web are not on the
  hackathon critical path).

---

## 4. What remains (all user-gated)

| # | Step | Est. | Ready? |
|---|---|---|---|
| 1 | **Catalog PR** against `NousResearch/hermes-agent`: fork + branch, add one file `plugin-catalog/privacy-pass.yaml` (draft with pinned SHA in `catalog/privacy-pass.yaml`), open the PR with the pre-drafted description in `docs/SUBMISSION.md` (includes rule-13 disclosures) | ~15 min | ready — entry drafted, SHA pinned, validation known-green |
| 2 | **Demo video** (<90 s): rehearse with `scripts/demo_gate.sh`, record per the `docs/DEMO.md` shot list (synthetic data only, stated on camera) | ~1 hr | shot list + rehearsal tooling ready |
| 3 | **X post** tagging `@NousResearch` with the video; keep the URL | ~10 min | — |
| 4 | **Typeform**: PR link + X post URL via the organizer form | ~5 min | — |
| 5 | **Confirm deadline** with organizers (flagged since day one — everything assumes Nov 11 5 p.m. EST is exact) | async | — |
| 6 | Respond to catalog reviewer feedback | unknown | the only remaining engineering work |

Buffer if submitted on schedule: opening the PR on Nov 7 leaves ~3–5 days of
review latency before the deadline, versus hours in the original plan.

---

## 5. Honest boundaries (carried into the demo and PR, not hidden)

- Auxiliary Hermes calls bypass sanitization entirely (platform boundary,
  counted and disclosed).
- Attachments/multimodal content: not protected (documented boundary).
- Detection is heuristic; misses are silent by nature. Protect list is the
  deterministic layer.
- Not HIPAA-compliant, not zero-leakage, not anonymity — claims we
  deliberately do not make (`docs/KNOWN_LIMITS.md`).

The strongest open risk is no longer technical: it is catalog review latency
and the unconfirmed deadline. Both argue for submitting tomorrow.
