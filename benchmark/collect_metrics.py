"""Adapt legacy psutil CPU/RSS measurement to client + Docker container samples."""

import csv
import json
import re
import statistics
import subprocess
import threading
import time

import psutil

from .common import utc_now


def memory_bytes(value):
    match = re.fullmatch(r"\s*([0-9.]+)\s*([KMGT]?i?B)\s*", value)
    if not match:
        raise ValueError("Unsupported Docker memory unit")
    units = {"B": 1, "kB": 1000, "KB": 1000, "MB": 1000**2, "GB": 1000**3, "TB": 1000**4,
             "KiB": 1024, "MiB": 1024**2, "GiB": 1024**3, "TiB": 1024**4}
    return int(float(match[1]) * units[match[2]])


def docker_sample():
    result = subprocess.run(["docker", "stats", "--no-stream", "--format", "{{json .}}", "pg-dpr"],
                            capture_output=True, text=True, timeout=10, check=True)
    data = json.loads(result.stdout)
    return {"db_cpu_percent_one_core": float(data["CPUPerc"].rstrip("%")),
            "db_ram_bytes": memory_bytes(data["MemUsage"].split("/")[0])}


class Collector:
    def __init__(self, path, interval=2):
        self.path, self.interval = path, interval
        self.stop = threading.Event()
        self.samples = []
        self.thread = None

    def start(self):
        self.thread = threading.Thread(target=self.collect, daemon=True)
        self.thread.start()

    def collect(self):
        process = psutil.Process()
        process.cpu_percent(None)
        fields = ("timestamp_utc", "db_cpu_percent_one_core", "db_ram_bytes", "client_cpu_percent_one_core",
                  "client_ram_bytes", "ok")
        with self.path.open("x", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=fields)
            writer.writeheader()
            while not self.stop.is_set():
                sample = {"timestamp_utc": utc_now(), "ok": True}
                try:
                    sample.update(docker_sample())
                    sample.update(client_cpu_percent_one_core=process.cpu_percent(None),
                                  client_ram_bytes=process.memory_info().rss)
                except Exception:
                    sample.update(ok=False)
                self.samples.append(sample)
                writer.writerow(sample)
                handle.flush()
                self.stop.wait(self.interval)

    def finish(self):
        self.stop.set()
        self.thread.join(timeout=15)
        good = [s for s in self.samples if s["ok"]]
        fields = ("db_cpu_percent_one_core", "db_ram_bytes", "client_cpu_percent_one_core", "client_ram_bytes")
        return {"samples": len(self.samples), "failed_samples": len(self.samples) - len(good),
                **{key + "_median": statistics.median(s[key] for s in good) if good else None for key in fields},
                **{key + "_peak": max(s[key] for s in good) if good else None for key in fields}}
