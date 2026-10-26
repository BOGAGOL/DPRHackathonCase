#!/usr/bin/env bash
set -Eeuo pipefail

: "${OPENBAO_ADDR:?required}"
: "${OPENBAO_TOKEN:?required}"
key_name="${OPENBAO_KEY_NAME:-customer-data}"

export BAO_ADDR="$OPENBAO_ADDR"
export BAO_TOKEN="$OPENBAO_TOKEN"

bao secrets list -format=json | grep -q '"transit/"' || bao secrets enable transit
bao write -f "transit/keys/$key_name"

policy_file="$(mktemp)"
trap 'rm -f "$policy_file"' EXIT
printf 'path "transit/encrypt/%s" { capabilities = ["update"] }\n' "$key_name" > "$policy_file"
printf 'path "transit/decrypt/%s" { capabilities = ["update"] }\n' "$key_name" >> "$policy_file"
bao policy write leakproof-app "$policy_file"

printf 'Transit key dan policy dibuat. Buat workload token melalui auth method organisasi.\n'

