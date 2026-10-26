#!/usr/bin/env bash
set -Eeuo pipefail

if docker compose exec -T openbao bao status >/dev/null 2>&1; then
  printf 'OpenBao sudah initialized dan unsealed.\n'
  exit 0
fi

printf '%s\n' \
  'Jalankan inisialisasi secara manual agar unseal keys tidak disalin otomatis:' \
  'docker compose exec openbao bao operator init -key-shares=3 -key-threshold=2' \
  '' \
  'Simpan keluaran pada media terpisah, lalu masukkan dua unseal key:' \
  'docker compose exec openbao bao operator unseal UNSEAL_KEY_1' \
  'docker compose exec openbao bao operator unseal UNSEAL_KEY_2' \
  '' \
  'Login dan aktifkan Transit:' \
  'docker compose exec openbao bao login ROOT_TOKEN_LAB' \
  'docker compose exec openbao bao secrets enable transit' \
  'docker compose exec openbao bao write -f transit/keys/customer-data'

