#!/bin/sh
# Privacy Pass offline egress gate — the demo rehearsal in one command.
#
# Boots the mock provider, a sandboxed Hermes with the plugin installed from
# the current working tree, sends the synthetic gate prompt, and asserts:
#   1. the effective provider payload contains no raw secrets
#   2. the user-facing reply is fully restored
# Exits non-zero on any failure. Safe to run repeatedly; no provider account.
set -eu

REPO=${REPO:-"$(cd "$(dirname "$0")/.." && pwd)"}
GATE_HOME=${GATE_HOME:-"/tmp/privacy-pass-demo-gate"}
CAPTURES=${CAPTURES:-"/tmp/privacy-pass-demo-captures"}
PORT=${PORT:-8765}
PROMPT="Ask Jane Doe about SSN 212-88-3456 or email jane.doe@example.com."
SECRETS="Jane Doe|212-88-3456|jane.doe@example.com"

echo "==> building sandbox $GATE_HOME"
# A stale gateway for this data root holds the state.db WAL and blocks
# startup after the sandbox is rebuilt. Match both /tmp and /private/tmp
# spellings (macOS symlink).
for pid in $(pgrep -f "gateway run --quiet --idle-exit"); do
    if ps -E -p "$pid" 2>/dev/null | grep -qE "HERMES_HOME=$GATE_HOME|HERMES_HOME=/private$GATE_HOME"; then
        kill "$pid" 2>/dev/null || true
    fi
done
sleep 1
rm -rf "$GATE_HOME" "$CAPTURES"
mkdir -p "$GATE_HOME/plugins/privacy-pass"
(cd "$REPO" && git archive HEAD 2>/dev/null || tar -cf - --exclude .venv --exclude .git .) \
    | tar -x -C "$GATE_HOME/plugins/privacy-pass"
find "$GATE_HOME/plugins" -name "__pycache__" -type d -exec rm -rf {} + 2>/dev/null || true

cat > "$GATE_HOME/config.yaml" <<EOF
model:
  provider: gate-mock
  model: mock-model
custom_providers:
  - name: gate-mock
    base_url: http://127.0.0.1:$PORT/v1
    api_key: dummy-not-a-real-key
    model: mock-model
EOF

# Plugins are opt-in by default — only enabled plugins load.
HERMES_HOME="$GATE_HOME" hermes plugins enable privacy-pass >/dev/null

echo "==> starting mock provider on :$PORT"
PRIVACY_PASS_CAPTURE_DIR="$CAPTURES" PRIVACY_PASS_MOCK_PORT="$PORT" \
    python3 "$REPO/tests/mock_provider.py" &
MOCK_PID=$!
trap 'kill $MOCK_PID 2>/dev/null || true' EXIT
sleep 1

echo "==> running one-shot Hermes turn"
REPLY=$(HERMES_HOME="$GATE_HOME" hermes -z "$PROMPT" --ignore-rules 2>&1 | tail -1)
echo "reply: $REPLY"

echo "==> asserting egress"
python3 - "$CAPTURES" "$REPLY" <<'PYEOF'
import glob, json, sys

caps, reply = sys.argv[1], sys.argv[2]
secrets = ["Jane Doe", "212-88-3456", "jane.doe@example.com"]
bodies = []
for f in glob.glob(caps + "/*.json"):
    try:
        bodies.append(json.load(open(f)))
    except ValueError:
        pass
main = [b for b in bodies if b.get("stream")]
aux = [b for b in bodies if not b.get("stream") and b.get("messages")]
fail = 0

if not main:
    print("FAIL: no main request captured")
    sys.exit(1)
main_blob = json.dumps(main)
for s in secrets:
    if s in main_blob:
        print(f"LEAK in main provider payload: {s}")
        fail = 1
    else:
        print(f"  ok: absent from main payload — {s}")
if aux:
    print(f"  NOTE: {len(aux)} auxiliary side-call(s) captured — known Hermes "
          "boundary, not plugin-fixable (docs/KNOWN_LIMITS.md)")
for s in secrets:
    if s in reply:
        print(f"  ok: restored in reply — {s}")
    else:
        print(f"MISSING from reply: {s}")
        fail = 1
for tok in ("<Person", "<SSN", "<Email", "<Protected", "<Company"):
    if tok in reply:
        print(f"ALIAS TOKEN visible in reply: {tok}")
        fail = 1

print("PASS: synthetic secrets absent from the main provider payload; reply fully restored."
      if not fail else "FAIL: do not record the demo until this is green.")
sys.exit(1 if fail else 0)
PYEOF
