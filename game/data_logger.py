from __future__ import annotations

import csv
import time
from pathlib import Path
from typing import Any


class DataLogger:
    def __init__(self) -> None:
        self.session_id = int(time.time())          # unique ID per game run
        self.event_types = {
            "attack_type":    "logs/attack_type.csv",
            "enemy_defeat":   "logs/enemy_defeat.csv",
            "hover_duration": "logs/hover_duration.csv",
            "damage_taken":   "logs/damage_taken.csv",
            "survival_time":  "logs/survival_time.csv",
            "ability_loss":   "logs/ability_loss.csv",
        }
        self.buffers: dict[str, list[dict[str, Any]]] = {
            key: [] for key in self.event_types
        }
        self.log_files = {
            key: Path(path) for key, path in self.event_types.items()
        }
        for log_file in self.log_files.values():
            log_file.parent.mkdir(parents=True, exist_ok=True)

        # Migrate old 3-column CSVs before anything else, then ensure headers
        for log_file in self.log_files.values():
            self._migrate_if_needed(log_file)
        self._ensure_headers()

    # ── Public API ─────────────────────────────────────────────────────────────

    def record_event(self, event_type: str, value: Any, timestamp_ms: int) -> None:
        if event_type not in self.buffers:
            return
        self.buffers[event_type].append({
            "session_id":   self.session_id,
            "timestamp_ms": timestamp_ms,
            "event_type":   event_type,
            "value":        value,
        })

    def save_to_csv(self) -> None:
        for event_type, buffer in self.buffers.items():
            if not buffer:
                continue
            log_file = self.log_files[event_type]
            with log_file.open("a", newline="", encoding="utf-8") as f:
                writer = csv.DictWriter(
                    f, fieldnames=self._new_fieldnames(), extrasaction="ignore"
                )
                writer.writerows(buffer)
            buffer.clear()

    # ── Helpers ────────────────────────────────────────────────────────────────

    def _new_fieldnames(self) -> list[str]:
        return ["session_id", "timestamp_ms", "event_type", "value"]

    def _migrate_if_needed(self, log_file: Path) -> None:
        """If the CSV exists with old 3-column header (no session_id), rewrite it
        with session_id=0 prepended to every row so old data shows as Legacy Data."""
        if not log_file.exists() or log_file.stat().st_size == 0:
            return
        try:
            with log_file.open("r", newline="", encoding="utf-8") as f:
                reader = csv.DictReader(f)
                if reader.fieldnames and "session_id" in reader.fieldnames:
                    return          # Already new format, nothing to do
                rows = list(reader)
        except Exception:
            return

        # Rewrite with session_id=0 (marks as Legacy Data in the dashboard)
        new_fields = self._new_fieldnames()
        try:
            with log_file.open("w", newline="", encoding="utf-8") as f:
                writer = csv.DictWriter(f, fieldnames=new_fields, extrasaction="ignore")
                writer.writeheader()
                for row in rows:
                    row.setdefault("session_id", 0)
                    writer.writerow(row)
        except Exception:
            pass

    def _ensure_headers(self) -> None:
        for log_file in self.log_files.values():
            if log_file.exists() and log_file.stat().st_size > 0:
                continue
            with log_file.open("w", newline="", encoding="utf-8") as f:
                writer = csv.DictWriter(f, fieldnames=self._new_fieldnames())
                writer.writeheader()