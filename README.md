# Privacy Pass

**Local privacy controls for AI conversations — starting with a native Hermes Agent plugin.**

**Status:** Project plan / pre-build specification  
**First release:** Hermes Agent plugin for the Nous Research Plugin Hackathon  
**Hackathon deadline:** November 11, 2026, 5:00 p.m. EST (November 12, 2026, 7:00 a.m. KST) — deadline from hackathon announcement; confirm with organizers before submission  
**Target platform:** macOS first; portable Python core  
**License target:** MIT, subject to a dependency and source-code license review

## 1. Product description

Privacy Pass detects selected private information in prompts, conversation history, and tool traffic **before it goes to an outside model or service**. It replaces detected values with stable aliases, keeps the alias-to-original map on the user's device, and restores the values in the response shown to the user where the integration allows it.

**Example (illustrative; not a guarantee that all medical facts are detected):**

| Stage | Text |
|---|---|
| User writes | `Ask Dr. Margaret Chen about Jane Doe's SSN 212-88-3456.` |
| Cloud-bound request | `Ask <Person 1> about <Person 2>'s SSN <SSN 1>.` |
| Model replies | `<Person 1> should confirm the request with <Person 2>.` |
| User sees | `Dr. Margaret Chen should confirm the request with Jane Doe.` |

Privacy Pass is **not** a promise that no private information will ever reach a provider. Detection can miss data, aliases can reduce accuracy, and integrations cannot protect routes they do not control. Security claims must be backed by tests that inspect the data actually sent.

### Why build it?

- People use cloud AI with names, contact details, health-related text, account numbers, work records, and files.
- Manually removing those details is slow and inconsistent.
- Simple redaction removes relationships the model needs to answer well.
- Local, consistent aliases can preserve much of the meaning without transmitting the original values.
- One privacy engine should work across several AI tools, not require Hermes for ordinary conversations.

### Product boundaries

Privacy Pass protects **only traffic that a supported adapter can see and control**. It does not claim to monitor all applications, block every network path, or provide HIPAA compliance. Avoid sending regulated or highly sensitive records until the specific workflow has been reviewed and tested.

## 2. Product strategy and delivery order

**The hackathon deliverable is a working, native Hermes Agent plugin.** The reusable Python core is its internal dependency, not a substitute for the plugin. Future adapters use the same core.

| Component | What it does | Phase |
|---|---|---|
| Privacy Pass Core | Detection, aliasing, mapping, restoration, policy, local audit | Build now |
| Hermes adapter | Native Hermes middleware/hooks; protects model requests and selected tool traffic | **Hackathon submission** |
| Browser extension | Protects supported ChatGPT, Claude, Gemini browser workflows before Send; restores displayed aliases where feasible | After hackathon, feasibility first |
| Local API gateway | A local endpoint that forwards compatible API requests after filtering and restores compatible responses | After hackathon |
| macOS companion | User-initiated protected paste/send, clipboard or accessibility workflows for desktop apps | Later; research first |
| Native desktop integrations | Use official extension points if vendors expose suitable interception controls | Only when supported |

**Important distinction:** ChatGPT, Claude, and Gemini desktop apps do **not** share a general third-party pre-send interception API. An MCP tool is not an always-on interception layer. A macOS companion may help with text entry, but it cannot promise complete control over app messages, attachments, history, or hidden context. Likewise, a local proxy covers only clients that can route their traffic through it; TLS interception of proprietary apps is not the default design.

## 3. Hackathon outcome and definition of done

A user can install and enable Privacy Pass as a Hermes plugin. During a Hermes session, the plugin:

1. Rewrites the **complete cloud-bound LLM request** at the final request middleware boundary, not just the latest user turn.
2. Assigns consistent aliases within a session, including repeated names across turns.
3. Retains original values and mappings locally; the cloud request contains aliases for all supported, detected fields.
4. Restores known aliases in user-facing text without exposing mappings to the model.
5. Protects, blocks, or asks approval for sensitive **outbound** tool arguments where supported; handles tool results before later cloud model use.
6. Produces a local, privacy-safe audit summary with no raw private values.
7. Fails closed on errors at sensitive egress boundaries, with a clear notice to the user.
8. Passes Hermes plugin validation and has an end-to-end test showing the **actual outbound payload** contains no known test secrets.
9. Includes installation instructions, limits, a short working demo, and the required hackathon submission links.

**Day-one technical gate:** prove that the adapter can mutate the full outgoing model request *and* that a captured fake secret is absent from the effective provider payload. Hook registration or detection logs alone do not prove protection.

## 4. Architecture

```text
Hermes user / tools / conversation history
                  |
                  v
         Hermes Plugin Adapter
       (lifecycle hooks + middleware)
                  |
                  v
        Privacy Pass Core (Python)
       +---------------------------+
       | Detection and policy      |
       | Session alias registry    |
       | Sanitization / restoration|
       | Local audit and settings  |
       +---------------------------+
                  |
           Cloud-bound request
          (only sanitized content)
                  |
           External LLM provider
                  |
             Model response
                  |
       Hermes response transform
                  |
          Restored user display
```

### Hermes integration points

The following use **public Hermes extension surfaces**. Exact callback fields, return structures, and ordering must be checked against the installed Hermes release during implementation.

| Surface | Intended job | Priority |
|---|---|---|
| `llm_request` middleware | Inspect and rewrite **all** provider-bound messages or Responses API `input`, including history and tool-result content | P0 |
| `tool_request` middleware | Rewrite or block eligible tool arguments before execution; preserve argument structure | P0 for outbound tools |
| `transform_tool_result` hook | Sanitize sensitive tool output before the model consumes it again; verify actual ordering | P0 |
| `transform_llm_output` hook | Restore aliases in the text shown to the user; handle held streaming safely | P0 |
| `pre_llm_call` hook | Policy/session preparation and observability, **not** the only egress guard | P1 |
| `post_api_request` hook | Local, non-sensitive request counts and status; no message bodies | P1 |
| Slash command (`/privacy`) | Show status, mode, and counts; support explicit enable/disable as policy allows | P1 |
| Hermes Desktop surface | Small status panel if time allows | P2 |

Hermes documents `llm_request` as operating on full provider arguments and `tool_request` as operating before tool execution. Do not rely on `pre_tool_call` alone to rewrite tool arguments. See [Middleware](https://hermes-agent.nousresearch.com/docs/developer-guide/middleware), [Plugin developer guide](https://hermes-agent.nousresearch.com/docs/developer-guide/plugins), and [Hooks](https://hermes-agent.nousresearch.com/docs/user-guide/features/hooks).

### What must be protected

- Current user text **and all prior messages** in the payload.
- Tool results and any later inclusion of tool content in an LLM request.
- Tool arguments sent to **external** services such as web search or remote APIs.
- Summaries, system/developer content, retrieved files, and other context that can carry private data where the adapter exposes them.
- Attachments, multimodal inputs, embeddings, speech, and binary content: **not protected in v1** unless a separate adapter proves it can inspect and rewrite them. Warn or block unsupported risky routes rather than implying coverage.

### Important tool-call rule

Do **not** blindly replace values inside filesystem paths, command strings, IDs, or structured API parameters. Doing so can break tools or change their purpose. Classify tool fields by destination and type. Protect free-text outbound content by default; block or require user approval when an external action cannot work with aliases. Keep purely local file operations functional, and sanitize their results before any later remote LLM call.

### Implementation findings — November 6, 2026

Verified against installed Hermes v0.22.7 and the working tree:

- **Hermes middleware is fail-open by design** (exceptions are logged and the raw request proceeds). Fail-closed is therefore implemented *inside* the `llm_request` handler: any error returns a request whose conversation content (`messages`, `input`, `prompt`, `tools`, `tool_choice`) is replaced by a block notice.
- **Presidio's US_SSN recognizer deliberately rejects canonical placeholder SSNs** such as `123-45-6789` (published example numbers are on its deny-list). Demos and tests must use plausible synthetic SSNs that pass SSA validity rules, e.g. `212-88-3456`. The §1 example was updated accordingly.
- **Dependency isolation via sidecar runtime** (`python_runtime: external`): hermes-agent pins `numpy==2.5.4` while presidio-analyzer requires `numpy<2.5`, so the shared environment can never host this plugin's deps. The plugin owns a sidecar venv under `~/.hermes/plugins_data/privacy-pass/venv`, bootstrapped on first registration; the shared Hermes environment is never modified.
- The plugin adds only its own directory and the sidecar's site-packages to `sys.path`. If first-run bootstrap fails, Hermes disables the plugin and traffic flows unprotected — documented risk; installation must be verified with `hermes plugins doctor`.
- Protect-list entities alias as `<Protected N>`; NER-detected entities as `<Person N>`, `<Company N>`, `<Email N>`, `<SSN N>`, etc. The word "SSN" itself can be NER-aliased as `<Company 1>` (noise, not a leak); refine via a default skip list.
- Session registry guarantees: aliases stable across turns; sanitization is **idempotent on its own output** (aliases are never re-detected); SSN/card formats sharing digits share one alias; unknown aliases (`<Person 99>`) are never fabricated on restore; restoration is display-only.
- `hermes plugins doctor` and `hermes plugins validate --install-deps` pass on the current tree.
- **Day-one gate PASSED live (November 6).** `tests/mock_provider.py` (stdlib OpenAI-compatible mock, streaming SSE) plus a sandboxed `HERMES_HOME` proves the full loop end-to-end: the main chat request reaches the provider with aliases only (zero raw name/SSN/email), the system prompt keeps tool names intact (structured-only policy), and the reply is fully restored with no alias tokens left. Re-runnable offline; no provider tokens needed.
- **Gateway staleness gotcha:** a running `gateway` daemon keeps plugin modules loaded in memory — plugin file changes appear to have no effect until the gateway restarts. Document in DEMO/KNOWN_LIMITS; restart the gateway after updating the plugin.
- **System messages use the structured-only policy** (protect list + structured recognizers, no open-ended NER): full NER on Hermes' system prompt aliased every tool name and brand (`<Company N>`) and shifted conversation alias counters — noise that degrades model quality. Conversation messages keep the full policy.
- **Auxiliary calls confirmed unsanitizable:** `agent/auxiliary_hooks.py` states `pre_auxiliary_call`/`post_auxiliary_call` are observer-only (returns ignored, fail-open) — titling, compression, vision, and approval calls bypass sanitization by construction and carry raw user text (confirmed in the live capture). The plugin counts them via `pre_auxiliary_call` and `/privacy` reports the number; recommended user mitigation: `auxiliary.title_generation.enabled: false`. This is a hard product boundary to document, not a bug we can fix from a plugin.
- **`transform_llm_output` contract verified from installed source** (`agent/turn_finalizer.py`): payload keys `response_text, session_id, model, platform, turn_id`; the hook returns a plain replacement string (first non-empty wins). With `hold_stream=True`, a failed callback withholds the reply — display-side failure cannot leak pre-restore text. Hermes persists the *restored* text and replays it next turn; the middleware re-sanitizes that history with the same registry, keeping the round trip alias-stable.
- **Hermes writes full request-body dumps to local logs on API errors** (`dump_api_request_debug`: preflight, non-retryable client error, max retries). Dumps observe the payload *after* middleware mutation and pass through Hermes' own secret redaction — so they contain aliases, not raw values. Document in KNOWN_LIMITS; no code change needed.
- Pending verification: spaCy *model* package license; user-facing protect-list configuration.

## 5. Core engine: reuse existing code

The existing Privacy Pass project is reported at `/Users/jrgarrigues/repo/privacypass`. This path and the module behavior come from the supplied project context packet; **the actual repository has not been inspected or tested for this README**.

| Existing module | Intended use |
|---|---|
| `sanitizer.py` | Four-tier detection, identity linking, mapping, restore |
| `coarsen.py` / `generalize.py` | Optional domain-specific generalization |
| `dates.py` | Optional consistent date shifting; **off by default** |
| `sessions.py` | Local persistence; adapt rather than silently replacing format |
| `server.py` | Existing MCP tool interface; optional external adapter, not automatic coverage |
| `ingest.py` | Text extraction; attachments remain out of v1 egress protection until verified |
| `web.py` | Existing manual review UI; not part of hackathon critical path |

The existing Tier 4 semantic detector is a stub, not a working feature. Current entity detection relies on explicit protect terms, structured patterns, and Presidio/spaCy. Review the implementation and tests before copying code into the plugin.

### Core contracts (proposed)

```python
result = sanitize(text, protect_list=..., skip_list=...,
                  shift_calendar=False, apply_generalize=False)
# result.sanitized_text, result.mapping, result.detections ...

restored = reveal(sanitized_response, mapping, date_shifts=None)
```

These are existing interfaces described in the source packet. Add a thin **session-scoped registry** around them so repeated values get the same aliases across turns. Never reassign `<Person 1>` to a different person in the same session. Resolve alias collisions, repeated surnames, and concurrency explicitly.

### Detection policy for v1

- **Include:** protect list; person names; emails; phone numbers; US SSNs; payment card numbers; selected addresses and organizations; IP addresses where appropriate.
- **Review before adding:** blood-type regexes can match ordinary letters (`A`, `B`, `O`) and create false positives. Doctor names can use existing name detection plus contextual tests rather than a broad title regex.
- **Optional:** military-domain coarsening as a user-controlled feature; date shifting off by default.
- **Not claimed:** complete PHI detection, correct medical context, reliable secret detection in arbitrary binary files, or guaranteed anonymity after data is combined with outside facts.

Do not silently turn on destructive generalization. Keep the original meaning when possible, and document when a policy changes facts rather than merely substituting labels.

## 6. Privacy and security rules

### Hard requirements

1. **Fail closed:** if the privacy layer cannot inspect or rewrite a cloud-bound request, block that request rather than pass through raw content. Provide an explicit, clearly labeled override only if designed and tested.
2. **Minimum local storage:** use session mapping and counts; default audit entries must omit raw text, original values, full prompts, and restored replies.
3. **Local storage permissions:** restrict mapping files to the current user; define retention, reset, and purge behavior. Do not assume plain JSON files are encrypted at rest.
4. **No model-based privacy decision in v1:** do not call a cloud model to decide what to sanitize.
5. **Output restoration is bounded:** substitute only exact, known aliases; escape literal user text and prevent accidental or nested substitutions. Do not restore values in commands, URLs, or structured content that will be executed or sent out again.
6. **Provider selection is not proof of locality:** only skip sanitizing when the actual request destination is confirmed local and no upstream remote fallback is possible. Default to protection when unsure.
7. **Tool safety:** a web search using `<Person 1>` may return poor results. Block or require consent when aliasing makes a tool call invalid rather than silently send altered arguments.
8. **No misleading compliance claims:** do not call the product HIPAA-compliant or claim zero leakage without formal assessment. Use synthetic data in demos and tests.
9. **Protect attachments and logs:** document uncovered channels; do not emit sensitive payloads in debug traces or exceptions.
10. **Test secret egress:** use a controlled mock provider/tool to capture effective outgoing payloads and check that seeded secrets never appear.

### Local-model bypass

A verified local-only model may use an optional bypass. For the hackathon, **default to filtering even local-model requests unless the destination is confirmed local**. No data should be routed to a remote fallback without reapplying the filter.

### Sensitive modes (proposed)

| Mode | Behavior |
|---|---|
| Personal (default) | Alias supported detected data; fail closed when processing breaks |
| Work | Personal plus optional user-selected generalization rules |
| Strict | Block outbound calls with unsupported sensitive fields or low-confidence handling; allow explicit user review |

These modes are *policies*, not claims of complete coverage.

## 7. Repository layout (actual, November 6)

The plugin root **is the repository root** — the catalog pins a self-contained tree, Hermes expects a flat layout, and vendoring the core beside the entrypoint avoids a duplicated copy that could drift.

```text
privacypassplugin/            # published as privacy-pass
├── plugin.yaml               # Hermes manifest (python_runtime: external)
├── __init__.py               # register(ctx) entrypoint
├── middleware.py             # llm_request sanitize; fail closed in-handler
├── hooks.py                  # transform_llm_output restore (display only)
├── commands.py               # /privacy status (counts only)
├── bootstrap.py              # sidecar venv setup (presidio/spaCy/model)
├── README.md
├── LICENSE                   # MIT
├── pyproject.toml            # dev/test deps; sidecar deps live in bootstrap.py
├── privacy_pass/             # vendored core (copied from the privacypass repo)
│   ├── __init__.py
│   ├── sanitizer.py          # tiered detection + aliasing (+ session alias support)
│   ├── registry.py           # session-scoped stable aliases, idempotency
│   ├── policy.py             # modes; dates/generalization off by default
│   ├── engine.py             # per-session state, counts-only audit
│   ├── coarsen.py
│   ├── generalize.py
│   └── dates.py
└── tests/
    ├── test_sanitizer.py     # inherited from the original repo
    ├── test_dates.py         # inherited
    ├── test_coarsen.py       # inherited
    ├── test_registry.py      # stability, idempotency, bounded restore
    └── test_hermes_egress.py # day-one gate: fake secrets absent from payload
```

Server/web/ingest modules (`server.py`, `web.py`, `ingest.py`) stay in the original `/Users/jrgarrigues/repo/privacypass` checkout; they are not on the hackathon critical path. Check that the installed plugin can import the core **without depending on the developer's local checkout** — the vendored copy guarantees it.

## 8. Project plan — re-baselined November 6, 2026

Work started November 6 in Korea, one day behind the original plan; the calendar below is shifted accordingly. Submission is due November 12 at 7:00 a.m. Korea time if the announcement's **EST** deadline is exact. Aim to submit November 11 KST rather than relying on the final hours. The scope-control rule applies from today: the desktop panel, extra detectors, and local bypass are cut.

| Date (KST) | Deliverable | Exit test |
|---|---|---|
| **Nov 6** | Inspect core and installed Hermes API; create repo/package; minimal plugin; day-one gate | A fake SSN entered through the middleware does **not** appear in the effective cloud request *(done at middleware-contract level; live capture pending)* |
| **Nov 7** | Full `llm_request` sanitization hardening; session alias registry polish; response restoration verified in real Hermes | Multiple turns preserve stable aliases; responses show original names locally |
| **Nov 8** | Tool request policy; outbound tool guard; tool result sanitization | Remote tool arguments are safe or blocked; local file reads don't break |
| **Nov 9** | Fail-closed edge cases; safe audit persistence; settings; `/privacy status` live | Injection, error, bypass and concurrency tests pass |
| **Nov 10** | Integration and regression tests; package from clean checkout; documentation | `hermes plugins doctor` and `hermes plugins validate ... --install-deps` pass; clean-install test succeeds |
| **Nov 11** | Demo capture (under 90 seconds); open public repo and pinned catalog PR; post on X and submit form | Demo shows captured outbound data, restored result, and tool policy; PR/links accessible |
| **Nov 12** | Final buffer before the 7:00 a.m. KST deadline | Submission links confirmed; no known high-severity leakage in tested paths |

### Milestone A — Repository and core

- [ ] Inspect the current code; run its existing tests; record any broken imports/dependencies.
- [ ] Extract the shared core into a package; preserve existing behavior as much as possible.
- [ ] Add a session registry, policy module, and synthetic fixtures.
- [ ] Define a single adapter-facing API (`sanitize_request`, `sanitize_tool_call`, `restore_response`).

### Milestone B — Native Hermes plugin (hackathon requirement)

- [ ] Create a valid `plugin.yaml` and `register(ctx)` entrypoint.
- [ ] Register `llm_request` middleware and inspect the real effective provider request shape.
- [ ] Cover both `messages` and `input` request forms if used by the installed backend.
- [ ] Add `tool_request` middleware and tool-result handling.
- [ ] Add a response transform with no streaming leaks.
- [ ] Add a status command and audit counts.
- [ ] Test on a fresh Hermes profile, with no local development path dependencies.

### Milestone C — Quality and submission

- [ ] Capture exact outbound request/tool payloads in tests using **fake** names and identifiers.
- [ ] Cover multi-turn history, token streaming, malformed data, overlapping detectors, restart, parallel sessions, and unexpected provider/tool formats.
- [ ] Verify that unsupported routes either block or show an accurate warning.
- [ ] Document setup, threat model, limits, modes, and data deletion.
- [ ] Record the demo, push a public repo, pin a commit, open the catalog PR, and submit links.

## 9. Test cases and acceptance checks

| Scenario | Required behavior |
|---|---|
| Name, email, SSN in prompt | Original values absent from captured cloud request |
| Same name across five turns | Stable alias throughout session; no raw history leakage |
| Tool returns a document with PII | Later outgoing LLM request has sanitized tool content |
| Web search with raw PII in arguments | Sanitized safe query or blocked call |
| Local path with a person's name | Local operation is not silently corrupted |
| Model emits `<Person 1>` | User sees mapped name in display; future cloud requests remain sanitized |
| Model emits unknown `<Person 99>` | No fabricated identity is inserted |
| Streaming reply | Original values are never pushed to an unintended remote sink during restoration |
| Missing engine/dependency | Remote request stops with a clear error |
| Two active sessions | No alias-map crossover |
| Unsupported attachment | Clear warning/block; no claim that attachment was sanitized |
| Logs and crashes | No original values or full private messages written to audit/debug files |
| Fresh installation | Plugin loads and works without source checkout present |

**Evidence to retain:** sanitized capture logs with synthetic test strings, test results, validation output, and a reproducible demo script. Keep real user data out of evidence.

## 10. Setup — first implementation action

### User install (once the repository is public)

```bash
hermes plugins install jgarr16/privacy-pass
hermes plugins enable privacy-pass
hermes plugins doctor privacy-pass        # must pass; first start bootstraps the sidecar venv (~150 MB, one time)
```

Configure under `plugins.entries.privacy-pass.settings` in `config.yaml`
(read at registration; reload the plugin after changing):

```yaml
plugins:
  entries:
    privacy-pass:
      settings:
        protect_list:
          - "Jane Doe"
          - "CWO3 | Chief Warrant Officer"   # synonyms on one line, | separated
        skip_list: []
        mode: personal
```

Verify: `/privacy` answers with counts (always — a silent plugin means no
protection), and the offline egress proof in `docs/DEMO.md` reproduces the
captured-payload check without a provider account. Recommended companion
setting: `auxiliary.title_generation.enabled: false` (Hermes auxiliary
calls cannot be sanitized by any plugin — see docs/KNOWN_LIMITS.md).

This is a plan, not a claim that files have been created in the existing local repository. Start by checking the actual installed Hermes version and current Privacy Pass code.

```bash
hermes --version
hermes plugins list
cd /Users/jrgarrigues/repo/privacypass
ls -la
```

After inspecting the repo, choose packaging so the Hermes plugin can install independently. For local development, use a copy or editable package; do not move the only working code. Validate with commands from the current Hermes docs:

```bash
hermes plugins doctor /path/to/privacy-pass/adapters/hermes
hermes plugins validate /path/to/privacy-pass/adapters/hermes --install-deps
```

`doctor` is an early load test. `validate` is the stronger catalog admission check. Verify command availability against the installed Hermes version.

## 11. Hackathon submission

The source packet says the submission requires **all three**:

1. A pull request to the Hermes plugin catalog.
2. A working demo video **under 90 seconds**, posted on X and tagging `@NousResearch`.
3. Both links sent through the organizer's [Typeform](https://form.typeform.com/to/FwJLvOln).

The announcement states **November 11, 2026, 5 p.m. EST** as the deadline. This remains event-specific information from the supplied packet and should be checked against the latest official announcement.

### Current catalog rules verified November 5, 2026

The Hermes catalog docs specify:

- Host the plugin in a public GitHub or GitLab repo.
- Make it loadable at an exact pinned commit; include `plugin.yaml` and an entrypoint.
- Use public plugin APIs; do not patch Hermes core or Desktop files at runtime.
- Run `hermes plugins validate /path/to/plugin --install-deps`.
- Open a PR against `NousResearch/hermes-agent` adding **one** `plugin-catalog/<name>.yaml` catalog entry; pin the exact full 40-character SHA; disclose required capabilities and security behavior.
- Let catalog CI and maintainers review the pinned tree. **Opening the PR is submission, not a guarantee of acceptance.**

See [catalog submission guide](https://hermes-agent.nousresearch.com/docs/developer-guide/plugins/catalog-submission) and [plugin guide](https://hermes-agent.nousresearch.com/docs/developer-guide/plugins).

### Demo script (target: 75–85 seconds)

| Time | Show |
|---|---|
| 0:00–0:12 | User types a synthetic private prompt in Hermes |
| 0:12–0:35 | Captured provider payload shows stable aliases, with original test values absent |
| 0:35–0:50 | Hermes responds; user-facing display restores mapped values |
| 0:50–1:05 | Remote tool request gets rewritten or blocked |
| 1:05–1:20 | Status/audit counts, safe local storage, and plain limitations |

Prioritize **proof of actual interception** over an animated dashboard or a speculative privacy score.

## 12. Risks and decisions

| Risk | Severity | Decision |
|---|---|---|
| Missed PII from imperfect detectors | High | Do not claim complete coverage; protect lists, test corpus, strict policy, optional user review |
| Full conversation history bypasses latest-turn filter | High | Sanitize the final complete provider-bound request on every call |
| Alternate model/tool/attachment route bypasses adapter | High | Inventory routes and fail closed or mark unsupported |
| Tool argument rewrite breaks a command | High | Classify external vs local, fields vs free text; block when uncertain |
| Mapping file leaks PII | High | Store minimally with strict permissions and deletion support; assess encryption later |
| Cross-session alias collisions | High | Session registry with tests and per-session isolation |
| Provider response output format changes | Medium | Test streaming, structured output, and known alias substitution boundaries |
| Presidio/spaCy install too heavy | Medium | Keep a tested structured-pattern path; make NER optional only if risk disclosed |
| Unverified local provider bypass | High | Keep protection on unless endpoint is confirmed local-only |
| Limited hackathon time | High | No browser extension, macOS GUI, or desktop panel on the critical path |

### Decisions already made

- Hermes plugin is the **hackathon product**.
- Shared core is independent of Hermes.
- Future browser, API, and macOS desktop integrations remain part of the product plan.
- Reuse existing Privacy Pass detection and aliasing code.
- Protect complete outbound requests, not only the final user message.
- Dates are optional and off by default.
- Sanity Check integration is not part of the hackathon entry.

### Decisions that require implementation evidence

- Exact Hermes callback signatures and whether all backend paths reach middleware.
- Which tool argument fields can safely be rewritten.
- Whether response restoration works in every Hermes Desktop, CLI, and gateway stream path.
- Session persistence format, encryption approach, and deletion controls.
- Packaging method for the shared core in a catalog-installed plugin.
- Whether any desktop app supports a safe, official input hook in a future adapter.

## 13. After the hackathon

**Release 1: Browser proof of concept.** Choose one web app; detect Send reliably; route only user-entered text through local Privacy Pass; restore response text where practical. Confirm what is *not* covered (attachments, voice, history sync, custom features). Expand to other sites only after end-to-end tests.

**Release 2: Local API gateway.** Build a localhost-only gateway with authentication, explicit allowed clients, provider-specific protocol adapters, streaming tests, and no request-body logging. Support OpenAI/Anthropic/Gemini API workflows only where clients can configure the endpoint. A gateway cannot automatically capture closed desktop-app traffic.

**Release 3: macOS companion.** Start with a user-triggered “Protect and Paste” action for desktop apps. Consider accessibility-assisted workflows only after app-specific security and reliability tests. Do not promise universal, invisible monitoring.

**Release 4: Wider distribution.** Improve detectors, cross-platform support, storage encryption, review UI, documentation, policy controls, and security tests before calling it a general privacy product.

## 14. Source notes

This README is based on the supplied **“Conversation Context Packet: Privacy Pass × Hermes Agent Plugin Hackathon”** (581 lines) and the later decision to support non-Hermes clients in the long term. The existing repository was **not** inspected; descriptions of its behavior remain source-reported, not verified implementation facts.

Current Hermes documentation checked November 5, 2026:

- [Build a Hermes Plugin](https://hermes-agent.nousresearch.com/docs/developer-guide/plugins)
- [Hermes Middleware](https://hermes-agent.nousresearch.com/docs/developer-guide/middleware)
- [Hermes Event Hooks](https://hermes-agent.nousresearch.com/docs/user-guide/features/hooks)
- [Submitting to the Plugin Catalog](https://hermes-agent.nousresearch.com/docs/developer-guide/plugins/catalog-submission)

---

**First build gate:** capture one real Hermes cloud-bound provider request with synthetic PII and prove Privacy Pass removed the original values before transmission.
