"""Loads harmful (and optionally benign) behavior strings from a benchmark CSV.

The tool ships no behaviors of its own. Point this at a CSV from a published,
audit-oriented benchmark — e.g. HarmBench's `harmbench_behaviors_text_all.csv`
or JailbreakBench's `harmful-behaviors.csv` / `benign-behaviors.csv`. The text
column is auto-detected (HarmBench: "Behavior"; JailbreakBench: "Goal").
"""
from __future__ import annotations

import csv
from pathlib import Path

from ..constants import BEHAVIOR_TEXT_COLUMNS


def _detect_text_column(fieldnames: list[str]) -> str:
    for column in BEHAVIOR_TEXT_COLUMNS:
        if column in fieldnames:
            return column
    raise ValueError(
        f"No behavior-text column found in {fieldnames}. "
        f"Expected one of: {', '.join(BEHAVIOR_TEXT_COLUMNS)}."
    )


def load_behaviors(csv_path: str | Path, limit: int = 0) -> list[str]:
    with open(csv_path, encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        if not reader.fieldnames:
            raise ValueError(f"{csv_path} has no header row")
        column = _detect_text_column(list(reader.fieldnames))
        behaviors = [row[column].strip() for row in reader if row.get(column, "").strip()]
    return behaviors[:limit] if limit else behaviors
