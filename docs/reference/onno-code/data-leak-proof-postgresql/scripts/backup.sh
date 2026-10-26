#!/usr/bin/env bash
set -Eeuo pipefail

: "${DATABASE_URL:?required}"
: "${BACKUP_AGE_RECIPIENT:?required}"
backup_dir="${BACKUP_DIR:-backups}"
backup_stamp="$(date -u +%Y%m%dT%H%M%SZ)"
plain_file="$backup_dir/leakproof-$backup_stamp.dump"
encrypted_file="$plain_file.age"
mkdir -p "$backup_dir"
umask 077

pg_dump --format=custom --file="$plain_file" "$DATABASE_URL"
sha256sum "$plain_file" > "$plain_file.sha256"
age --recipient "$BACKUP_AGE_RECIPIENT" --output "$encrypted_file" "$plain_file"
sha256sum "$encrypted_file" > "$encrypted_file.sha256"

printf 'Backup terenkripsi: %s\n' "$encrypted_file"
printf 'File plaintext sementara masih ada: %s\n' "$plain_file"
printf 'Hapus secara aman hanya setelah enkripsi, checksum, katalog, dan restore drill diverifikasi.\n'

