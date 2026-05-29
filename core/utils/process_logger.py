import os
import datetime
import threading


class ProcessLogger:
    """
    Writes a timestamped, structured process log to {output_dir}/process.log.

    Every agent, orchestrator, and runner calls this logger so the full
    execution trace — screenshots, LLM calls, decisions, results — is
    visible in a single human-readable file without exception.

    Usage:
        logger = ProcessLogger(output_dir)
        logger.log("OBSERVER", "Screenshot taken", detail=raw_path)
        logger.log("DECIDER", "ActionPlan", detail=plan_json)
        logger.separator()
    """

    LEVEL_WIDTH = 14   # component name column width

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

    def log(self, component: str, message: str, detail: str = ""):
        """
        Write one log entry.

        :param component: Agent/component name, e.g. "OBSERVER", "EXECUTOR".
        :param message:   One-line summary of the event.
        :param detail:    Optional multi-line detail (action plan JSON, reasoning, etc.).
        """
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
