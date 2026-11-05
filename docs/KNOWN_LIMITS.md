# Known limits

Plain statements of what Privacy Pass v0.1.0 does **not** do. These are
boundaries, not aspirations — each was verified against installed Hermes
v0.22.7 (see README §4 findings).

## Coverage

- **Auxiliary LLM calls bypass sanitization entirely.** Titling, compaction,
  MoA advisor calls, vision, and approval calls go through
  `agent.auxiliary_client`; its hooks (`pre_auxiliary_call` /
  `post_auxiliary_call`) are documented observer-only (returns ignored,
  fail-open). Confirmed live: an auxiliary request carried the raw user
  message. `/privacy` counts them; reduce them with
  `auxiliary.title_generation.enabled: false` in config.yaml.
- **Attachments and multimodal content are not protected.** Images, files,
  audio, and embeddings pass through untouched. The middleware leaves
  non-text content parts in place rather than claiming coverage.
- **Detection misses are silent by nature.** Heuristics (protect list,
  structured regexes, spaCy NER) miss things; an undetected value is sent.
  There is no way to fail closed on what was never detected. Add personal
  names you care about to `protect_list` for deterministic handling.
- **Canonical placeholder SSNs are deliberately rejected** by Presidio's
  US_SSN recognizer (`123-45-6789` and friends are on its deny-list).
  Testing with published example numbers makes detection look broken; use
  plausible synthetic values (e.g. `212-88-3456`).
- **NER false positives exist.** Tool names and common words can be aliased
  in conversation messages (`SSN` → `<Company 1>`). System messages use the
  structured-only policy to avoid mangling Hermes' own tool lists; add
  offenders to `skip_list`.

## Behavior

- **Aliases reduce task accuracy.** A web search for `<Person 1>` returns
  poor results. External free-text arguments are aliased anyway (privacy
  first); protect-list values in external tool arguments are blocked outright
  via `pre_tool_call`.
- **Tool results from the web use structured-only sanitization.** Third-party
  names in web pages stay readable; your protect-list values and structured
  identifiers do not.
- **Restoration is display-only.** Restored text is what Hermes persists and
  replays next turn; it is re-sanitized by the middleware with the same
  session registry. Never pipe restored output into another outbound tool.
- **One alias per value per session, never reassigned.** Sessions are keyed
  by Hermes `session_id`; alias counters restart per session by design.

## Operations

- **The gateway daemon caches loaded plugin modules.** After updating plugin
  files, restart the gateway — otherwise edits silently have no effect.
- **Config changes require a reload.** `protect_list` / `skip_list` / `mode`
  under `plugins.entries.privacy-pass.settings` are read at registration.
- **If the plugin fails to load, traffic flows unprotected.** Hermes
  disables a crashing plugin and continues. Run `hermes plugins doctor`
  after install; `/privacy` should always answer.
- **Mapping files are 0600 JSON, not encryption.** They contain everything
  needed to restore aliases; delete the sessions directory to purge.
- **Dependencies are heavy (~150 MB sidecar)**: presidio-analyzer, spaCy,
  en_core_web_sm in a plugin-owned venv (`python_runtime: external`) because
  hermes-agent pins numpy 2.5.4 and presidio requires <2.5. The shared
  Hermes environment is never modified.
- **First registration downloads the sidecar** — expect a one-time
  multi-minute wait on the first start.

## Claims we deliberately do not make

- Not HIPAA-compliant; no formal compliance assessment exists.
- Not zero-leakage; the egress tests prove the tested paths only.
- Not anonymous; aliased output preserves structure and categories.
- Not an always-on system-wide filter; only Hermes surfaces this plugin can
  see are covered.
