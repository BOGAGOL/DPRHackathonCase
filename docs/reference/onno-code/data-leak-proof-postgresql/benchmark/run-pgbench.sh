#!/usr/bin/env bash
set -Eeuo pipefail

: "${DATABASE_URL:?required}"
customer_count="${CUSTOMER_COUNT:-100000}"
clients="${CLIENTS:-16}"
jobs="${JOBS:-4}"
duration="${DURATION:-300}"
test_id="${TEST_ID:-T0-plaintext}"
run_id="${RUN_ID:-run-01}"
output_dir="results/$test_id/$run_id"
mkdir -p "$output_dir"

case "$test_id" in
  T0-plaintext)
    read_script="benchmark/read-plaintext.sql"
    update_script="benchmark/update-plaintext.sql"
    ;;
  *)
    read_script="benchmark/read-protected.sql"
    update_script="benchmark/update-protected.sql"
    ;;
esac

pgbench --no-vacuum --client="$clients" --jobs="$jobs" --time=60 \
  --file="$read_script" --define="customer_count=$customer_count" \
  "$DATABASE_URL" > "$output_dir/warmup.txt" 2>&1

benchmark/collect_metrics.sh "$DATABASE_URL" "$output_dir/before"

(
  cd "$output_dir"
  pgbench --no-vacuum --client="$clients" --jobs="$jobs" --time="$duration" \
    --progress=10 --report-per-command --log \
    --file="../../../$read_script@7" --file="../../../$update_script@3" \
    --define="customer_count=$customer_count" "$DATABASE_URL" \
    > pgbench.txt 2>&1
)

benchmark/collect_metrics.sh "$DATABASE_URL" "$output_dir/after"

