# Submission runbook (executes in ~15 minutes after repo push)

Everything below is user-gated (GitHub ownership, X account, Typeform).
Verify each command's flags against the current docs before running.

## 1. Publish

```bash
gh repo create jgarr16/privacy-pass --public --source=. --push
SHA=$(git rev-parse HEAD)   # pin this in the catalog entry
```

## 2. Catalog PR (one file: `plugin-catalog/privacy-pass.yaml`)

- Fork + branch `NousResearch/hermes-agent`, add the entry from
  `catalog/privacy-pass.yaml` (this repo holds the prepared draft) with the
  pinned `sha`.
- `version` must be **quoted** and match the pinned `plugin.yaml`.
- `requires_hermes: ">=0.22.0"` (verified on 0.22.7; never newer than the
  current release).
- Entry schema is canonical at `plugin-catalog/README.md#entry-schema` in
  the target repo — re-check fields against it before opening the PR; a
  test fails the build if they drift.

### PR description draft

> **What it does:** Privacy Pass detects private information in outbound
> Hermes traffic and replaces it with stable, session-local aliases before
> the provider sees it; responses are restored locally for display. The
> complete provider-bound request (all messages, history, Responses `input`,
> tool-call argument strings) is rewritten on every call. Free-text
> arguments of external tools are aliased; external calls carrying a raw
> protect-list value are blocked. Tool results are sanitized before the
> model consumes them. Fail-closed: if the privacy layer cannot verify a
> request, the request is blocked (implemented in-handler, because Hermes
> middleware is fail-open by design).
>
> **Hermes surfaces used:** `llm_request` + `tool_request` middleware;
> `transform_llm_output` (hold_stream), `pre_tool_call`,
> `transform_tool_result`, `pre_auxiliary_call` (observer: counts) hooks;
> `/privacy` command; `python_runtime: external` sidecar venv
> (`~/.hermes/plugins_data/privacy-pass/venv`, bootstrapped on first start).
>
> **Rule-13 disclosures:**
> - Network: plugin code makes no network calls of its own. Provider traffic
>   is the host's own LLM traffic, seen (and rewritten) by middleware.
>   First-start bootstrap downloads pinned Python dependencies
>   (presidio-analyzer, spacy, en_core_web_sm wheel) from PyPI/GitHub into
>   the plugin-owned venv; afterwards no downloads occur.
> - Out-of-scope reads: none. Writes: alias mappings to
>   `~/.hermes/plugins_data/privacy-pass/` (0600).
> - Shell commands: none at runtime beyond the one-time sidecar bootstrap
>   (`python -m venv`, `pip install`).
> - Background processes: none. Stored credentials: none. Telemetry: none.
>
> **Known limits (docs/KNOWN_LIMITS.md):** auxiliary Hermes calls (titling,
> compaction, vision) are observer-only surfaces and bypass sanitization —
> counted and disclosed via `/privacy`. Attachments/multimodal content is
> not protected. Detection is heuristic, not complete.

## 3. Pre-PR gates (must be green at the pinned SHA)

```bash
hermes plugins validate . --install-deps
uv run pytest
```

CI on our repo (`.github/workflows/ci.yml`) runs the same suite on every
push; catalog CI re-runs `hermes plugins validate` at the pinned commit.

## 4. Demo video (<90 s) → X → Typeform

- Record per `docs/DEMO.md` (synthetic data only; state it on camera).
- Post on X tagging `@NousResearch`; keep the URL.
- Submit PR link + post URL via the organizer Typeform.

## Review-risk notes (pre-answered)

- **First-start dependency bootstrap may read as self-updating.** It
  installs pinned dependencies into a plugin-owned venv once; it never
  updates plugin code. If reviewers want it moved to install-time, the
  fallback is a documented setup command instead of auto-bootstrap.
- **numpy conflict is the reason for the sidecar** (`python_runtime:
  external`): hermes-agent pins `numpy==2.5.4`; presidio requires `<2.5`.
  Shared-env installation is impossible by construction.
- Rule 9: the PR must be opened by the repo owner (`jgarr16`).
