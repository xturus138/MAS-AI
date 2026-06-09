import os
import datetime
import threading
from enum import IntEnum

from shared import config


class LogLevel(IntEnum):
    DEBUG = 10
    INFO  = 20
    WARN  = 30
    ERROR = 40


class ProcessLogger:
    """
    Writes a timestamped, structured process log to {output_dir}/process.log.

    Levels (default: INFO):
      DEBUG — verbose internal events (widget resolution, short-circuit logic, LLM call start)
      INFO  — step boundaries, final verdicts, failures
      WARN  — non-fatal issues
      ERROR — fatal errors

    Per-component thresholds are read from config at init (e.g. REFLECTOR_LOG_LEVEL=DEBUG).
    If not set, falls back to the global RUN_LOG_LEVEL env var, then INFO.
    """

    LEVEL_WIDTH = 14   # component name column width

    _COMPONENT_LEVELS: dict = {}

    @classmethod
    def _resolve_level(cls, component: str) -> LogLevel:
        """Return the effective LogLevel for a given component."""
        if component not in cls._COMPONENT_LEVELS:
            # Check per-component env var first (e.g. REFLECTOR_LOG_LEVEL)
            env_key = f"{component.upper()}_LOG_LEVEL"
            env_val = os.environ.get(env_key, "").upper()
            if env_val == "DEBUG":
                cls._COMPONENT_LEVELS[component] = LogLevel.DEBUG
            elif env_val in ("WARN", "WARNING"):
                cls._COMPONENT_LEVELS[component] = LogLevel.WARN
            elif env_val == "ERROR":
                cls._COMPONENT_LEVELS[component] = LogLevel.ERROR
            else:
                # Fall back to global RUN_LOG_LEVEL
                global_val = os.environ.get("RUN_LOG_LEVEL", "INFO").upper()
                cls._COMPONENT_LEVELS[component] = {
                    "DEBUG": LogLevel.DEBUG, "INFO": LogLevel.INFO,
                    "WARN": LogLevel.WARN, "WARNING": LogLevel.WARN, "ERROR": LogLevel.ERROR,
                }.get(global_val, LogLevel.INFO)
        return cls._COMPONENT_LEVELS[component]

    def __init__(self, output_dir: str):
        self._path = os.path.join(output_dir, "process.log")
        self._lock = threading.Lock()
        os.makedirs(output_dir, exist_ok=True)
        # Write header so the file exists immediately when the runner starts
        self._write_raw(
            f"{'=' * 80}\n"
            f"  MAS AI — Process Log\n"
            f"  Output: {output_dir}\n"
            f"  Started: {self._ts()}\n"
            f"{'=' * 80}\n\n"
        )

    # ── Public API ────────────────────────────────────────────────────────────

    def log(self, component: str, message: str, detail: str = "",
            level: LogLevel = LogLevel.INFO):
        """
        Write one log entry.

        :param component: Agent/component name, e.g. "OBSERVER", "EXECUTOR".
        :param message:   One-line summary of the event.
        :param detail:    Optional multi-line detail (action plan JSON, reasoning, etc.).
        :param level:     LogLevel.DEBUG/INFO/WARN/ERROR.  Default: INFO.
        """
        if level < self._resolve_level(component):
            return  # filtered

        tag = f"[{component.upper():<{self.LEVEL_WIDTH}}]"
        line = f"{self._ts()}  {tag}  {message}\n"
        if detail:
            for sub in str(detail).splitlines():
                line += f"{'':>30}  {sub}\n"
        self._write_raw(line)

    def separator(self, char: str = "─", width: int = 80):
        """Visual separator between cycle steps."""
        self._write_raw(char * width + "\n")

    def section(self, title: str):
        """Bold section header, e.g. 'CYCLE 3'."""
        self._write_raw(
            f"\n{'━' * 80}\n"
            f"  {title}\n"
            f"{'━' * 80}\n"
        )

    def close(self):
        """Write closing footer."""
        self._write_raw(
            f"\n{'=' * 80}\n"
            f"  Process Log Closed: {self._ts()}\n"
            f"{'=' * 80}\n"
        )

    # ── Internal ──────────────────────────────────────────────────────────────

    @staticmethod
    def _ts() -> str:
        return datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]

    def _write_raw(self, text: str):
        with self._lock:
            with open(self._path, "a", encoding="utf-8") as f:
                f.write(text)
