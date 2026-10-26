import argparse
import csv
import statistics
import time

import psycopg


def percentile(values, fraction):
    ordered = sorted(values)
    return ordered[round((len(ordered) - 1) * fraction)]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dsn", required=True)
    parser.add_argument("--tenant-id", required=True)
    parser.add_argument("--input", required=True, help="hex blind index per line")
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    with open(args.input, encoding="ascii") as source:
        indexes = [bytes.fromhex(line.strip()) for line in source if line.strip()]
    if not indexes:
        raise SystemExit("no benchmark input")

    latencies = []
    errors = 0
    with psycopg.connect(args.dsn) as connection, open(
        args.output, "w", newline="", encoding="utf-8"
    ) as output:
        writer = csv.DictWriter(
            output, fieldnames=["sequence", "operation", "latency_ms", "status"]
        )
        writer.writeheader()
        for sequence, email_bidx in enumerate(indexes, start=1):
            started = time.perf_counter_ns()
            status = "ok"
            try:
                connection.execute(
                    """
                    SELECT customer_id,email_payload
                    FROM protected_v2.customers_secure
                    WHERE tenant_id=%s AND email_bidx=%s
                    """,
                    (args.tenant_id, email_bidx),
                ).fetchone()
            except Exception as error:  # benchmark records errors; it does not hide them
                status = type(error).__name__
                errors += 1
            latency_ms = (time.perf_counter_ns() - started) / 1_000_000
            latencies.append(latency_ms)
            writer.writerow(
                {
                    "sequence": sequence,
                    "operation": "email_lookup",
                    "latency_ms": f"{latency_ms:.6f}",
                    "status": status,
                }
            )

    print(
        {
            "samples": len(latencies),
            "errors": errors,
            "p50_ms": percentile(latencies, 0.50),
            "p95_ms": percentile(latencies, 0.95),
            "p99_ms": percentile(latencies, 0.99),
            "mean_ms": statistics.fmean(latencies),
        }
    )


if __name__ == "__main__":
    main()

