# Demo — proof of actual interception

The demo's single job: show that the values Hermes sends are not the values
the user typed, and that what the user reads back is what they typed. No
dashboards, no privacy scores.

## Storyboard (target 75–85 seconds)

| Time | Beat | Proof shown |
|---|---|---|
| 0:00–0:12 | Type a synthetic private prompt in Hermes (`Ask Jane Doe about SSN 212-88-3456 or email jane.doe@example.com.`) | terminal |
| 0:12–0:35 | Show the captured effective provider payload | aliases only; original values absent |
| 0:35–0:50 | Hermes reply, restored | user sees `Jane Doe` / `212-88-3456`, no `<...>` tokens |
| 0:50–1:05 | External tool beat: a `web_search` with a protected value in the query — rewritten, and a second call blocked | middleware rewrite + `pre_tool_call` block notice |
| 1:05–1:20 | `/privacy` status + say the boundary out loud | counts, storage path, "auxiliary calls are not covered" |

All data on screen is synthetic. Say so on camera.

## Reproducible evidence (offline, no provider account)

The capture harness is the same one used for the day-one gate:

```bash
# terminal 1: mock provider (captures every request body)
PRIVACY_PASS_CAPTURE_DIR=/tmp/demo-captures python3 tests/mock_provider.py

# terminal 2: sandboxed Hermes pointed at the mock
HERMES_HOME=/tmp/demo-gate hermes plugins enable privacy-pass   # once
HERMES_HOME=/tmp/demo-gate hermes -z "Ask Jane Doe about SSN 212-88-3456 or email jane.doe@example.com." --ignore-rules
```

Assert before recording:

```bash
grep -r "Jane Doe\|212-88-3456" /tmp/demo-captures/ && echo "LEAK — do not record" || echo "clean"
```

The sandbox `HERMES_HOME` carries a `config.yaml` with a `custom_providers`
entry pointing at `http://127.0.0.1:8765/v1` (see README §4 findings for the
exact shape). Restart the gateway after touching plugin files — a running
gateway keeps old plugin modules in memory. And write `config.yaml` **before**
`hermes plugins enable` (or re-enable afterwards): the enablement record
lives in `config.yaml` under `plugins.enabled`, so overwriting the file
after enabling silently disables the plugin.

## Talking points

- What the provider sees: stable session aliases (`<Person 1>`, `<SSN 1>`),
  history included, every call.
- What the user sees: exact restoration, unknown aliases never fabricated.
- Failure behavior: middleware cannot verify → request is blocked, not sent.
- The boundary, on camera: "Hermes' own auxiliary calls and attachments are
  outside what any plugin can reach — we count and disclose them instead."
