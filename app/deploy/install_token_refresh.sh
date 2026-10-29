#!/usr/bin/env bash
# One-time operator install. Archive staging root is passed by the release wrapper.
set -euo pipefail
umask 077
test "$(id -un)" = ubuntu || { echo 'Run from the ubuntu SSH session.' >&2; exit 1; }
dpr_stage="$(cd -- "${1:?Pass the verified release staging directory}" && pwd)"
dpr_repo=/home/ubuntu/juara1onno
dpr_private="$HOME/dpr-demo-zhafif/private/module-a"
dpr_broker=/usr/local/lib/dpr-service-app/token_refresh.py
test -x "$dpr_repo/app/.venv/bin/python"
test -f "$dpr_private/handoff/app.env"
test ! -L "$dpr_repo/app/scripts/serve.py"
test ! -L "$dpr_repo/app/scripts/run_runtime.sh"
grep -q '^# DPR_SERVICE_APP_UNIT_V1$' /etc/systemd/system/dpr-api.service
sudo -v

# Hash checking precedes all changes. Different team changes are not overwritten.
/usr/bin/python3 - "$dpr_stage" "$dpr_repo" <<'PY'
import hashlib,json,sys
from pathlib import Path
stage,repo=map(Path,sys.argv[1:])
manifest=json.loads((stage/'manifest.json').read_text())
expected={'app/scripts/serve.py','app/scripts/run_runtime.sh','app/backend/service_app/token_source.py',
          'app/deploy/token_refresh.py','app/deploy/dpr-token-refresh.service',
          'app/deploy/dpr-token-refresh.timer','app/deploy/token-auto.conf',
          'app/deploy/install_token_refresh.sh'}
if set(manifest['files']) != expected: raise SystemExit('Unexpected release contents')
for name,digest in manifest['files'].items():
    path=stage/name
    if path.is_symlink() or hashlib.sha256(path.read_bytes()).hexdigest()!=digest:
        raise SystemExit('Release checksum mismatch')
for name,digest in manifest['base_files'].items():
    path=repo/name
    if path.is_symlink() or hashlib.sha256(path.read_bytes()).hexdigest() not in (digest,manifest['files'][name]):
        raise SystemExit('Runtime source changed; refusing replacement: '+name)
print('Release and current launchers verified.')
PY

for unit in dpr-token-refresh.service dpr-token-refresh.timer; do
  if sudo test -e "/etc/systemd/system/$unit"; then
    sudo grep -q '^# DPR_SERVICE_APP_TOKEN_REFRESH_V1$' "/etc/systemd/system/$unit"
  fi
done
if sudo test -e /etc/systemd/system/dpr-api.service.d/token-auto.conf; then
  sudo grep -q '^# DPR_SERVICE_APP_TOKEN_REFRESH_V1$' /etc/systemd/system/dpr-api.service.d/token-auto.conf
fi
sudo systemd-analyze verify "$dpr_stage/app/deploy/dpr-token-refresh.service" "$dpr_stage/app/deploy/dpr-token-refresh.timer"

dpr_backup="$HOME/dpr-demo-zhafif/private/service-b/token-autorefresh-backup/$(date -u +%Y%m%dT%H%M%SZ)"
install -d -m 0700 "$dpr_backup"
cp "$dpr_repo/app/scripts/serve.py" "$dpr_backup/serve.py"
cp "$dpr_repo/app/scripts/run_runtime.sh" "$dpr_backup/run_runtime.sh"
chmod 0600 "$dpr_backup/serve.py" "$dpr_backup/run_runtime.sh"

# The root bootstrap token is read only in this explicit, one-time setup invocation.
sudo install -d -o root -g root -m 0755 /usr/local/lib/dpr-service-app
sudo install -d -o root -g root -m 0700 /etc/dpr-service-app
sudo install -o root -g root -m 0644 "$dpr_stage/app/deploy/token_refresh.py" "$dpr_broker"
sudo /usr/bin/python3 -I "$dpr_broker" setup \
  --material "$dpr_private/openbao/init-material.json" \
  --operator-uid "$(id -u)" --gid "$(id -g)" \
  --ca "$dpr_private/tls/ca.crt"

# Runtime identities, DB state, account files, TLS certificates and keys stay intact.
for file in app/scripts/serve.py app/scripts/run_runtime.sh app/backend/service_app/token_source.py; do
  install -m 0644 "$dpr_stage/$file" "$dpr_repo/$file"
done
sudo install -d -o root -g ubuntu -m 0750 /run/dpr-service-app
sudo install -d -o root -g root -m 0755 /etc/systemd/system/dpr-api.service.d
sudo install -o root -g root -m 0644 "$dpr_stage/app/deploy/token-auto.conf" /etc/systemd/system/dpr-api.service.d/token-auto.conf
for unit in dpr-token-refresh.service dpr-token-refresh.timer; do
  sudo install -o root -g root -m 0644 "$dpr_stage/app/deploy/$unit" "/etc/systemd/system/$unit"
done
sudo systemctl daemon-reload
sudo systemctl start dpr-token-refresh.service
sudo systemctl enable --now dpr-token-refresh.timer
systemctl is-active dpr-api.service dpr-web.service dpr-token-refresh.timer

cd "$dpr_repo"
install -d -m 0700 app/.local app/evidence/access-control
sudo /usr/bin/python3 -I "$dpr_broker" status > app/.local/token-refresh-status.json

# Only existing smoke login/logout and GET operations; never provision/reset accounts/data.
dpr_smoke_rc=0
env -i HOME="$HOME" PATH="$PATH" DPR_SECRETS_DIR="$dpr_private" bash --noprofile --norc <<'BASH' || dpr_smoke_rc=$?
set -euo pipefail
set -a
. "$DPR_SECRETS_DIR/handoff/app.env"
set +a
app/.venv/bin/python app/scripts/pentest_smoke.py --evidence app/evidence/access-control/token-autorefresh-smoke.json
BASH

sudo systemctl start dpr-token-refresh.service
sudo /usr/bin/python3 -I "$dpr_broker" status > app/.local/token-refresh-second-check.json
/usr/bin/python3 - "$dpr_stage" <<'PY'
from datetime import datetime,timedelta,timezone
import json,subprocess,sys
from pathlib import Path
root=Path.cwd()
first=json.loads((root/'app/.local/token-refresh-status.json').read_text())
second=json.loads((root/'app/.local/token-refresh-second-check.json').read_text())
smoke_path=root/'app/evidence/access-control/token-autorefresh-smoke.json'
smoke=json.loads(smoke_path.read_text()) if smoke_path.exists() else {'passed':False}
manifest=json.loads((Path(sys.argv[1])/'manifest.json').read_text())
services={unit:subprocess.run(['systemctl','is-active',unit],capture_output=True,text=True).stdout.strip()
          for unit in ('dpr-api.service','dpr-web.service','dpr-token-refresh.timer')}
checks=smoke.get('checks',{})
passed=(first.get('passed') is True and second.get('passed') is True and not second.get('rotated')
        and not second.get('api_reloaded') and smoke.get('passed') is True
        and len(checks)==65 and all(value=='active' for value in services.values()))
report={'passed':passed,'source_commit':manifest['source_commit'],'mode':'protected',
        'database':'protected_734','first_tick':first,'second_tick':second,
        'smoke_passed':sum(v is True for v in checks.values()),'smoke_total':len(checks),
        'accounts_checked':smoke.get('accounts_checked'),'services':services,
        'root_used_for_setup_only':True,'credential_values_in_report':False,
        'keys_data_accounts_modified':False,'openbao_postgres_restarted':False,
        'completed_at_wib':datetime.now(timezone(timedelta(hours=7))).isoformat()}
destination=root/'app/evidence/access-control/vm-token-autorefresh.json'
destination.write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps({'passed':passed,'report':str(destination),'smoke':str(report['smoke_passed'])+'/'+str(report['smoke_total'])}))
raise SystemExit(0 if passed else 1)
PY
