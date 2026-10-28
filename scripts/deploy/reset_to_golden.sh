#!/usr/bin/env bash
# Explicitly authorized destructive reset of this application's DB only.
set -euo pipefail
test "${1:-}" = protected_734 || { echo 'Usage: bash scripts/deploy/reset_to_golden.sh protected_734' >&2; exit 2; }
test "$(id -un)" = ubuntu || { echo 'Run as ubuntu, not root' >&2; exit 1; }
dpr_repo="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd)"
test "$dpr_repo" = /home/ubuntu/juara1onno || { echo 'Unexpected checkout' >&2; exit 1; }
sudo -v
exec env -i HOME="$HOME" PATH="$HOME/dpr-demo-zhafif/runtime/node/bin:/usr/local/bin:/usr/bin:/bin" \
  DPR_SECRETS_DIR="$HOME/dpr-demo-zhafif/private/module-a" \
  bash --noprofile --norc -c '
    set -euo pipefail
    set -a
    . "$DPR_SECRETS_DIR/handoff/app.env"
    . "$DPR_SECRETS_DIR/handoff/setup.env"
    set +a
    cd "$1"
    exec "$1/app/.venv/bin/python" "$1/app/scripts/golden_reset.py" reset --confirm-target protected_734
  ' _ "$dpr_repo"
