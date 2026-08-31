"""Parses process.log (core/utils/process_logger.py's ProcessLogger format).

Line format: "{timestamp}  [{component:<14}]  {message}\n", where component
is right-padded to ProcessLogger.LEVEL_WIDTH (14) chars inside brackets.
Detail lines are indented continuations (30 spaces + text) and are folded
into the preceding entry's message rather than parsed as separate entries.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

_ENTRY_RE = re.compile(
    r"^(?P<timestamp>\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}\.\d{3})"
    r"\s{2}\[(?P<component>[A-Z_]+)\s*\]\s{2}(?P<message>.*)$"
)


@dataclass(frozen=True)
class LogEntry:
    timestamp: str
    component: str
    message: str


def parse_log_lines(text: str) -> list[LogEntry]:
    entries: list[LogEntry] = []
    for line in text.splitlines():
        match = _ENTRY_RE.match(line)
        if match:
            entries.append(
                LogEntry(
                    timestamp=match.group("timestamp"),
                    component=match.group("component"),
                    message=match.group("message").rstrip(),
                )
            )
    return entries


def filter_entries(entries: list[LogEntry], component: str | None = None) -> list[LogEntry]:
    if component is None:
        return list(entries)
    target = component.upper()
    return [entry for entry in entries if entry.component.upper() == target]
