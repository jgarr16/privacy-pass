# Privacy Pass — Security notes

Status: hackathon release (v0.1.0). This document describes the actual,
verified behavior of the code in this repository — including what it does
**not** do.

## Threat model

Privacy Pass addresses one narrow problem: **private information flowing
from a Hermes session to external LLM providers and external tools.**

Protected channels (verified by `tests/test_hermes_egress.py` and the
offline live gate in `tests/mock_provider.py`):

- The **complete provider-bound LLM request** — every message, including
  conversation history, system content, and assistant tool-call argument
  strings. Rewritten at the `llm_request` middleware boundary on every call.
- **Free-text arguments of external tools** (web search/extract) — aliased
  at the `tool_request` middleware boundary.
- **Tool results** — sanitized before the model consumes them again
  (`transform_tool_result`); user-file content gets the full detector,
  third-party web content the structured-only policy.
- The **user-facing reply** — alias restoration is display-only and
  substitutes exact, known aliases; unknown alias-like text is never
  fabricated.

## Fail-closed behavior

Hermes middleware is fail-open by design: a raising middleware is logged and
the raw request proceeds. Privacy Pass therefore implements fail-closed
**inside** the `llm_request` handler: any error returns a request whose
conversation content (`messages`, `input`, `prompt`, `tools`, `tool_choice`)
is replaced by a block notice. Unverified content is never sent.

The tool layer is intentionally fail-open for usability (a broken tool call
is not a privacy leak; the model only ever sees aliased context), with one
hard block: `pre_tool_call` blocks external tool calls whose arguments still
contain a raw protect-list value. Block messages never echo the value.

## Data handling

- Alias→original mappings live in memory and in owner-only files
  (`0600`, directory `0700`) under `~/.hermes/plugins_data/privacy-pass/sessions/`,
  keyed by a SHA-256 of the session id. Nothing is transmitted.
- Purge: delete that directory, or `SessionStore.purge()` from code.
  Retention: indefinite per session until purged — documented, not silent.
- Plain JSON is **not** encryption. The files are minimal and
  permission-restricted per the design constraint, not a cryptographic
  guarantee.
- Audit data is counts only. No message content, no original values, no
  full prompts are written by the plugin.
- No cloud model is consulted for detection decisions (local regex +
  Presidio/spaCy in a plugin-owned sidecar venv only).

## Verified non-coverage (read before trusting it with real data)

1. **Auxiliary LLM calls are not protected.** Hermes routes titling,
   compression, vision, and approval calls through `agent.auxiliary_client`,
   whose plugin hooks are observer-only (returns ignored, fail-open). These
   calls carry raw conversation text to the provider. The plugin counts them
   and `/privacy` reports the number. Mitigation:
   `auxiliary.title_generation.enabled: false`.
2. **Attachments, images, speech, and other binary content are not
   protected.** Non-text content parts pass through the middleware
   untouched; that boundary is deliberate and disclosed.
3. **Detection is heuristic.** Protect-list terms are deterministic;
   structured types (SSN, email, card, phone, IP) are reliable; NER person
   detection is probabilistic and will miss names, especially uncommon or
   non-Western ones. Detection misses are **not** fail-closed — an undetected
   value flows through.
4. **Hermes' own local storage and error-time request dumps** contain
   post-middleware (aliased) content on this device; session transcripts
   contain restored text by design. The plugin controls neither.
5. **Plugin not loaded = no protection.** If the sidecar bootstrap fails,
   Hermes disables the plugin and traffic flows unprotected. Verify with
   `hermes plugins doctor` after install.
6. **Aliases are not anonymity.** `<SSN 1>` preserves that a SSN exists;
   determined re-identification from combined context is out of scope.

## Reporting

Open a private GitHub security advisory on the repository (do not open a
public issue for exploitable leaks). Include the adapter surface, a
synthetic-data reproduction, and the Hermes version.
