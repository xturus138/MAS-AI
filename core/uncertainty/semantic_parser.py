"""Parse Observer SEMANTIC_MAP text into {element_id: semantic_string}.

Tolerant of [ID], [[ID]], and [start-end] range forms. Malformed lines are
skipped (never fabricated). The SUMMARY line is ignored.
"""
import re

_LINE_RE = re.compile(r"^\s*\[+\s*(\d+)\s*(?:-\s*(\d+)\s*)?\]+\s*:\s*(.+?)\s*$")


def parse_semantic_map(raw_text) -> dict:
    result = {}
    if not raw_text or not isinstance(raw_text, str):
        return result
    for line in raw_text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.upper().startswith("SUMMARY"):
            continue
        m = _LINE_RE.match(stripped)
        if not m:
            continue
        start = int(m.group(1))
        end = int(m.group(2)) if m.group(2) else start
        desc = m.group(3).strip()
        if end < start:
            start, end = end, start
        for i in range(start, end + 1):
            result[i] = desc
    return result
