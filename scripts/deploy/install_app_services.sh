#!/usr/bin/env bash
# Install only the two application units; never stop other host services.
set -euo pipefail
test "$(id -un)" = ubuntu || { echo 'Run as ubuntu, not sudo bash' >&2; exit 1; }
dpr_repo="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd)"
test "$dpr_repo" = /home/ubuntu/juara1onno || { echo 'Unexpected checkout path' >&2; exit 1; }
test -x "$dpr_repo/app/.venv/bin/python"
test -x "$HOME/dpr-demo-zhafif/runtime/node/bin/node"
test -f "$HOME/dpr-demo-zhafif/private/module-a/handoff/app.env"
if test -n "$(ss -H -ltn '( sport = :8100 or sport = :3443 )')"; then
  echo 'App ports are in use. Stop only foreground API/web with Ctrl+C first.' >&2
  exit 1
fi
for unit in dpr-api.service dpr-web.service; do
  if test -e "/etc/systemd/system/$unit" && ! grep -q '^# DPR_SERVICE_APP_UNIT_V1$' "/etc/systemd/system/$unit"; then
    echo 'An existing unit is not owned by this deployment; refusing replacement.' >&2
    exit 1
  fi
done
sudo -v
sudo systemd-analyze verify "$dpr_repo/app/deploy/dpr-api.service" "$dpr_repo/app/deploy/dpr-web.service"
for unit in dpr-api.service dpr-web.service; do
  sudo install -o root -g root -m 0644 "$dpr_repo/app/deploy/$unit" "/etc/systemd/system/$unit"
done
sudo systemctl daemon-reload
sudo systemctl enable --now dpr-api.service dpr-web.service
systemctl is-active dpr-api.service dpr-web.service
curl --fail --silent --show-error --retry 15 --retry-connrefused --retry-delay 1 \
  --connect-timeout 3 --max-time 5 \
  --cacert "$HOME/dpr-demo-zhafif/private/module-a/tls/ca.crt" \
  --output /dev/null https://127.0.0.1:3443/api/health/ready
