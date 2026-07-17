#!/usr/bin/env bash
# Prove the agent-engine loop closes end-to-end WITHOUT a real model.
# A stub "claude" on PATH fixes the sandbox bug, so the command gate goes green.
set -euo pipefail
cd "$(dirname "$0")/.."
. .venv/bin/activate

STUB_DIR="$(mktemp -d)"
cat > "$STUB_DIR/claude" <<'EOF'
#!/usr/bin/env bash
# Minimal stub: find the sandbox calc.py under CWD and fix a-b -> a+b, then emit JSON.
f="$(find . -name calc.py 2>/dev/null | head -1 || true)"
[ -n "$f" ] && sed -i '' 's/a - b/a + b/' "$f" 2>/dev/null || true
printf '{"type":"result","result":"fixed calc.py","usage":{"input_tokens":10,"output_tokens":5}}'
EOF
chmod +x "$STUB_DIR/claude"

PATH="$STUB_DIR:$PATH" loom run examples/agent-coding.loom.yaml --fresh
echo "smoke: exit $?"
