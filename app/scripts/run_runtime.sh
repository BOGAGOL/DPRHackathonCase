#!/usr/bin/env bash
set -euo pipefail
mode="${1:-}"
case "$mode" in api|web) ;; *) echo 'Use api or web' >&2; exit 2 ;; esac
dpr_repo="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd)"
exec env -i HOME="$HOME" PATH="$HOME/dpr-demo-zhafif/runtime/node/bin:/usr/local/bin:/usr/bin:/bin" \
  DPR_SECRETS_DIR="$HOME/dpr-demo-zhafif/private/module-a" \
  bash --noprofile --norc -c '
    set -euo pipefail
    set -a
    . "$DPR_SECRETS_DIR/handoff/app.env"
    set +a
    cd "$2"
    case "$1" in
      api) exec "$2/app/.venv/bin/python" -B "$2/app/scripts/serve.py" ;;
      web)
        unset MODE DATABASE_URL AUTH_DATABASE_URL ANALYST_DATABASE_URL AUDITOR_DATABASE_URL
        unset OPENBAO_ADDR OPENBAO_CACERT OPENBAO_TOKEN DPR_CRYPTO_FACTORY
        cd "$2/app/web"; exec npm start ;;
    esac
  ' _ "$mode" "$dpr_repo"
