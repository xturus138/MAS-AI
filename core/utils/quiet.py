"""Central log-noise suppression.

Import this module FIRST in main.py (before any heavy third-party import) so the
environment variables take effect before torch / transformers / ultralytics load.

It does two things:
  1. Sets env vars + logging levels that quiet YOLO, transformers and torch.
  2. Wraps sys.stdout to drop a handful of raw ``print()`` lines that the
     Canny / EasyOCR / vision pipeline emits every cycle (image size,
     filtered_boxes, YOLO speed, etc.) — lines we cannot silence any other way.

Everything else (agent narrative, cost trackers) passes through untouched.
"""

import os
import sys
import logging
import warnings

# ── 1. Quiet third-party libraries via env + logging ───────────────────────
os.environ.setdefault("YOLO_VERBOSE", "False")              # ultralytics detection logs
os.environ.setdefault("TRANSFORMERS_VERBOSITY", "error")    # Florence-2 generate warnings
os.environ.setdefault("TRANSFORMERS_NO_ADVISORY_WARNINGS", "1")

warnings.filterwarnings("ignore")

for _name in ("transformers", "ultralytics", "torch", "PIL", "easyocr"):
    logging.getLogger(_name).setLevel(logging.ERROR)

# ── 2. Drop known-noisy raw stdout lines ───────────────────────────────────
_NOISE_PREFIXES = (
    "image size:",
    "len(filtered_boxes):",
    "time to get parsed content:",
    "Speed:",
    "0: ",                                    # YOLO per-image detection summary
    "The following generation flags",
    "`torch_dtype` is deprecated",
)


class _FilteredStdout:
    """Stdout proxy that swallows lines matching the noise prefixes.

    ``print()`` writes the line body and the trailing newline as two separate
    ``write()`` calls, so when a body is dropped we also drop the single blank
    write that follows it (and nothing else).
    """

    def __init__(self, wrapped):
        self._wrapped = wrapped
        self._drop_next_blank = False

    def write(self, text):
        stripped = text.lstrip()
        if stripped == "":
            if self._drop_next_blank:
                self._drop_next_blank = False
                return len(text)
            return self._wrapped.write(text)
        if any(stripped.startswith(p) for p in _NOISE_PREFIXES):
            self._drop_next_blank = True
            return len(text)
        self._drop_next_blank = False
        return self._wrapped.write(text)

    def flush(self):
        self._wrapped.flush()

    def __getattr__(self, name):
        return getattr(self._wrapped, name)


# Install once (idempotent — avoid double-wrapping on re-import).
if not isinstance(sys.stdout, _FilteredStdout):
    sys.stdout = _FilteredStdout(sys.stdout)
