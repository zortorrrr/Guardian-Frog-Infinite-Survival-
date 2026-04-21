from __future__ import annotations

import csv
from pathlib import Path
from typing import Any


class DataLogger:
    def __init__(self) -> None:
        self.event_types = {
            "attack_type": "logs/attack_type.csv",
            "enemy_defeat": "logs/enemy_defeat.csv",
            "hover_duration": "logs/hover_duration.csv",
            "damage_taken": "logs/damage_taken.csv",
            "survival_time": "logs/survival_time.csv",
            "ability_loss": "logs/ability_loss.csv",   # discard vs hit
        }
        self.buffers: dict[str, list[dict[str, Any]]] = {key: [] for key in self.event_types}
        self.log_files = {key: Path(path) for key, path in self.event_types.items()}
        for log_file in self.log_files.values():
            log_file.parent.mkdir(parents=True, exist_ok=True)
        self._ensure_headers()

    def record_event(self, event_type: str, value: Any, timestamp_ms: int) -> None:
        if event_type not in self.buffers:
            return
        self.buffers[event_type].append(
            {
                "timestamp_ms": timestamp_ms,
                "event_type": event_type,
                "value": value,
            }
        )

    def save_to_csv(self) -> None:
        for event_type, buffer in self.buffers.items():
            if not buffer:
                continue
            log_file = self.log_files[event_type]
            with log_file.open("a", newline="", encoding="utf-8") as f:
                writer = csv.DictWriter(f, fieldnames=["timestamp_ms", "event_type", "value"])
                writer.writerows(buffer)
            buffer.clear()

    def _ensure_headers(self) -> None:
        for event_type, log_file in self.log_files.items():
            if log_file.exists() and log_file.stat().st_size > 0:
                continue
            with log_file.open("w", newline="", encoding="utf-8") as f:
                writer = csv.DictWriter(f, fieldnames=["timestamp_ms", "event_type", "value"])
                writer.writeheader()