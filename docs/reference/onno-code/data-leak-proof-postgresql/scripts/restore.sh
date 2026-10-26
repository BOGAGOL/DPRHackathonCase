#!/usr/bin/env bash
set -Eeuo pipefail

if [[ "$#" -ne 2 ]]; then
  printf 'usage: %s BACKUP.dump.age RESTORE_DATABASE_URL\n' "$0" >&2
  exit 2
fi

: "${AGE_IDENTITY_FILE:?required}"
encrypted_file="$1"
restore_dsn="$2"
temporary_dir="$(mktemp -d)"
trap 'rm -rf -- "$temporary_dir"' EXIT
plain_file="$temporary_dir/restore.dump"

age --decrypt --identity "$AGE_IDENTITY_FILE" --output "$plain_file" "$encrypted_file"
pg_restore --exit-on-error --clean --if-exists --no-owner --dbname="$restore_dsn" "$plain_file"
psql "$restore_dsn" -X --file=sql/50-validation.sql
printf 'Restore SQL selesai. Lanjutkan validasi OpenBao, decrypt sampel, RLS, dan aplikasi.\n'

