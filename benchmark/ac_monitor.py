"""Low-cost continuous AC samples plus Windows Kernel-Power 105 verification."""
import csv
from datetime import datetime
import json
from pathlib import Path
import subprocess
import threading
import time

import psutil

from .common import ROOT, utc_now, write_json


def power_events(start, end):
    for value in (start, end):
        if datetime.fromisoformat(value).tzinfo is None:
            raise ValueError("Power window must include timezone")
    completed = subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-File",
        str(ROOT / "benchmark/read_power_window.ps1"), "-StartUtc", start, "-EndUtc", end],
        capture_output=True, text=True, check=True, timeout=30)
    return json.loads(completed.stdout)


def qualify(samples, events):
    states = [row["ac_online"] for row in samples]
    return {"qualified": bool(states) and all(state is True for state in states)
            and events["latest_event_at_or_before_start"]["ac_online"] is True
            and all(row["ac_online"] is True for row in events["events_in_window"]),
            "samples": len(states), "samples_not_confirmed_ac": sum(s is not True for s in states),
            "kernel_power_false_events": sum(r["ac_online"] is False for r in events["events_in_window"]),
            "prior_kernel_event_ac_online": events["latest_event_at_or_before_start"]["ac_online"]}


class ACMonitor:
    def __init__(self, raw, evidence, interval=2):
        self.raw, self.evidence, self.interval = Path(raw), Path(evidence), interval
        self.samples = []
        self.stop = threading.Event()
        self.thread = None
        self.collection_failure = None

    def sample(self):
        battery = psutil.sensors_battery()
        row = {"timestamp_utc": utc_now(), "ac_online": battery.power_plugged if battery else None}
        self.samples.append(row)
        return row

    def require_ac(self):
        if self.collection_failure or self.sample()["ac_online"] is not True or any(row["ac_online"] is not True for row in self.samples):
            raise ValueError("AC supply not continuously confirmed; no automatic retry")

    def start(self):
        self.raw.mkdir(parents=True, exist_ok=True)
        self.started_at = utc_now()
        self.require_ac()
        initial = power_events(self.started_at, self.started_at)
        if initial["latest_event_at_or_before_start"]["ac_online"] is not True:
            raise ValueError("Kernel-Power does not confirm initial AC state")
        self.thread = threading.Thread(target=self.collect, daemon=True)
        self.thread.start()

    def collect(self):
        try:
            with (self.raw / "ac_samples.csv").open("x", encoding="utf-8", newline="") as handle:
                writer = csv.DictWriter(handle, fieldnames=("timestamp_utc", "ac_online"))
                writer.writeheader()
                while not self.stop.is_set():
                    writer.writerow(self.sample())
                    handle.flush()
                    self.stop.wait(self.interval)
        except Exception as error:
            self.collection_failure = type(error).__name__
            self.stop.set()

    def finish(self):
        self.sample()
        end = utc_now()
        self.stop.set()
        if self.thread:
            self.thread.join(timeout=5)
        time.sleep(1)  # Allow event delivery; not part of a measured interval.
        events = power_events(self.started_at, end)
        result = {"started_at_utc": self.started_at, "completed_at_utc": end,
                  "sample_interval_s": self.interval, **qualify(self.samples, events), "kernel_power": events,
                  "collection_failure": self.collection_failure,
                  "scope": "AC samples every 2s and phase guards; prior Kernel-Power105 AC=true and no AC=false event in whole session; not electrical fault instrumentation"}
        result["qualified"] = result["qualified"] and self.collection_failure is None and not (self.thread and self.thread.is_alive())
        write_json(self.raw / "ac_all_samples.json", self.samples)
        write_json(self.evidence / "power_verification.json", result)
        write_json(self.raw / "power_verification.json", result)
        return result
