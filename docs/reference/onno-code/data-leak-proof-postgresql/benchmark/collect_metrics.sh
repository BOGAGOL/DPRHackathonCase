#!/usr/bin/env bash
set -Eeuo pipefail

if [[ "$#" -ne 2 ]]; then
  printf 'usage: %s DSN OUTPUT_DIR\n' "$0" >&2
  exit 2
fi

benchmark_dsn="$1"
output_dir="$2"
mkdir -p "$output_dir"

date --iso-8601=seconds > "$output_dir/timestamp.txt"
uname -a > "$output_dir/uname.txt"
lscpu > "$output_dir/lscpu.txt"
free -h > "$output_dir/memory.txt"
lsblk -o NAME,TYPE,SIZE,FSTYPE,MOUNTPOINTS > "$output_dir/storage.txt"
psql "$benchmark_dsn" -X -c "SELECT version();" > "$output_dir/postgresql-version.txt"
psql "$benchmark_dsn" -X --csv -c \
  "SELECT name,setting,unit,source FROM pg_settings ORDER BY name" \
  > "$output_dir/pg-settings.csv"
psql "$benchmark_dsn" -X --csv -c \
  "SELECT * FROM pg_stat_database WHERE datname=current_database()" \
  > "$output_dir/pg-stat-database.csv"
psql "$benchmark_dsn" -X --csv -c "SELECT * FROM pg_stat_wal" \
  > "$output_dir/pg-stat-wal.csv"
psql "$benchmark_dsn" -X --csv -c "SELECT * FROM pg_stat_io" \
  > "$output_dir/pg-stat-io.csv"
psql "$benchmark_dsn" -X --csv -c \
  "SELECT * FROM pg_stat_statements ORDER BY total_exec_time DESC LIMIT 100" \
  > "$output_dir/pg-stat-statements.csv"

