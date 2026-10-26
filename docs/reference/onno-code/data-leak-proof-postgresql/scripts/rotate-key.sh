#!/usr/bin/env bash
set -Eeuo pipefail

: "${OPENBAO_ADDR:?required}"
: "${OPENBAO_TOKEN:?required}"
key_name="${OPENBAO_KEY_NAME:-customer-data}"
export BAO_ADDR="$OPENBAO_ADDR"
export BAO_TOKEN="$OPENBAO_TOKEN"

bao write -f "transit/keys/$key_name/rotate"
bao read "transit/keys/$key_name"
printf '%s\n' \
  'Rotasi selesai untuk enkripsi baru.' \
  'Jalankan rewrap bertahap, validasi, dan petakan backup sebelum membatasi versi lama.'

