"""Reads/writes the desktop app's managed .env file for the Settings screen.

Field list mirrors shared/config.py's documented env vars. Values that
shared/config.py only reads once at import time (nearly all of these) do
NOT take effect in the current process until restart -- the Settings screen
(Task 13) is responsible for surfacing that, this module only persists text.
"""

from __future__ import annotations

from desktop_app.paths import env_file_path

SETTINGS_FIELDS: list[str] = [
    "TARGET_DEVICE",
    "OBSERVER_PROVIDER", "OBSERVER_MODEL", "OBSERVER_API_KEY", "OBSERVER_BASE_URL",
    "DECIDER_PROVIDER", "DECIDER_MODEL", "DECIDER_API_KEY", "DECIDER_BASE_URL",
    "REFLECTOR_PROVIDER", "REFLECTOR_MODEL", "REFLECTOR_API_KEY", "REFLECTOR_BASE_URL",
    "ORCHESTRATOR_PROVIDER", "ORCHESTRATOR_MODEL", "ORCHESTRATOR_API_KEY", "ORCHESTRATOR_BASE_URL",
    "FIGMA_ACCESS_TOKEN", "FIGMA_URL_QA",
    "OBSERVER_DETECTION_METHOD",
]


def _parse_env_text(text: str) -> dict[str, str]:
    values: dict[str, str] = {}
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, _, value = stripped.partition("=")
        values[key.strip()] = value.strip()
    return values


def read_settings() -> dict[str, str]:
    path = env_file_path()
    if not path.is_file():
        return {}
    all_values = _parse_env_text(path.read_text(encoding="utf-8"))
    return {key: value for key, value in all_values.items() if key in SETTINGS_FIELDS}


def write_settings(values: dict[str, str]) -> None:
    path = env_file_path()
    existing = _parse_env_text(path.read_text(encoding="utf-8")) if path.is_file() else {}
    existing.update(values)
    lines = [f"{key}={existing[key]}" for key in sorted(existing)]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
