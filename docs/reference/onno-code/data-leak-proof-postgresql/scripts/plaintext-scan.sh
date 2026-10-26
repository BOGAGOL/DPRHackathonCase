#!/usr/bin/env bash
set -Eeuo pipefail

: "${DATABASE_URL:?required}"
scan_dir="${SCAN_DIR:-results/plaintext-scan}"
mkdir -p "$scan_dir"
dump_file="$scan_dir/protected.sql"
patterns_file="${PLAINTEXT_PATTERNS_FILE:-benchmark/plaintext-patterns.example}"

pg_dump --schema=protected_v2 --format=plain --file="$dump_file" "$DATABASE_URL"

if [[ ! -f "$patterns_file" ]]; then
  printf 'Buat %s berisi satu nilai sintetis per baris.\n' "$patterns_file" >&2
  exit 2
fi

findings=0
while IFS= read -r pattern; do
  [[ -z "$pattern" ]] && continue
  if rg --fixed-strings --quiet -- "$pattern" "$dump_file"; then
    printf 'FOUND pattern=%q\n' "$pattern"
    findings=$((findings + 1))
  fi
done < "$patterns_file"

printf 'findings=%d\n' "$findings"
exit "$((findings > 0))"

