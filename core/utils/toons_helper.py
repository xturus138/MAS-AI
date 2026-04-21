import json
from toons import dumps as toons_dumps
from core.utils.token_counter import count_tokens_in_text

_MAGENTA = "\033[95m"
_GREEN   = "\033[92m"
_YELLOW  = "\033[93m"
_RESET   = "\033[0m"
_BOLD    = "\033[1m"


def compress_and_report(data, label: str, agent: str) -> str:
    original_str      = json.dumps(data, ensure_ascii=False, separators=(",", ":"))
    compressed_str    = toons_dumps(data)
    original_tokens   = count_tokens_in_text(original_str)
    compressed_tokens = count_tokens_in_text(compressed_str)

    if original_tokens > 0:
        saved = original_tokens - compressed_tokens
        pct   = (saved / original_tokens) * 100
        color = _GREEN if pct >= 10 else _YELLOW
        print(
            f"{_MAGENTA}[TOONS]{_RESET} {_BOLD}{agent.upper()}{_RESET} | {label}: "
            f"{original_tokens} -> {color}{compressed_tokens} tokens{_RESET} "
            f"({color}-{saved} / {pct:.1f}% saved{_RESET})"
        )

    return compressed_str
