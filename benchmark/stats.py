"""Per-run metrics first, then medians; no pooled-run percentile substitution."""

import math
import statistics


def percentile(values, quantile):
    if not values or not 0 <= quantile <= 1:
        raise ValueError("Invalid percentile input")
    ordered = sorted(values)
    position = (len(ordered) - 1) * quantile
    lower, upper = math.floor(position), math.ceil(position)
    return ordered[lower] + (ordered[upper] - ordered[lower]) * (position - lower)


def summarize(latencies, errors, elapsed):
    if not latencies or elapsed <= 0 or not 0 <= errors <= len(latencies):
        raise ValueError("Invalid run samples")
    return {"requests": len(latencies), "errors": errors, "error_rate": errors / len(latencies),
            "p50_ms": percentile(latencies, .50), "p95_ms": percentile(latencies, .95),
            "p99_ms": percentile(latencies, .99), "mean_ms": statistics.mean(latencies),
            "throughput_rps": (len(latencies) - errors) / elapsed, "elapsed_s": elapsed}


def medians(runs):
    if not runs:
        raise ValueError("No runs")
    fields = ("p50_ms", "p95_ms", "p99_ms", "mean_ms", "throughput_rps", "error_rate")
    return {field: statistics.median(row[field] for row in runs) for field in fields}
