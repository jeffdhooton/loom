#!/usr/bin/env bash
# Prove the fleet supervisor runs 2 members in parallel, isolated, WITHOUT a
# real model. A stub "claude" on PATH fixes each member's sandbox copy, so
# both members' command gates go green independently.
set -uo pipefail
cd "$(dirname "$0")/.."
. .venv/bin/activate

STUB_DIR="$(mktemp -d)"
cat > "$STUB_DIR/claude" <<'EOF'
#!/usr/bin/env bash
# Minimal stub: find the sandbox calc.py under CWD (the member's own
# worktree) and fix a-b -> a+b, then emit print-mode JSON.
f="$(find . -name calc.py 2>/dev/null | head -1 || true)"
[ -n "$f" ] && sed -i '' 's/a - b/a + b/' "$f" 2>/dev/null || true
printf '{"type":"result","result":"fixed","usage":{"input_tokens":10,"output_tokens":5}}'
EOF
chmod +x "$STUB_DIR/claude"

# Reset the sandbox bug and prune any stale worktrees from prior runs so
# both members get a clean, isolated worktree this time.
git -C examples/sandbox checkout main -- calc.py
git -C examples/sandbox worktree prune

PATH="$STUB_DIR:$PATH" setpoint fleet run examples/fleet-demo.yaml --fresh
setpoint fleet status examples/fleet-demo.yaml
