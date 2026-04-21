import tiktoken
from typing import Any, List

_ENCODING_CACHE = {}

def _get_encoding(model: str = "gpt-4o"):
    if model not in _ENCODING_CACHE:
        try:
            enc = tiktoken.encoding_for_model(model)
        except KeyError:
            enc = tiktoken.get_encoding("cl100k_base")
        _ENCODING_CACHE[model] = enc
    return _ENCODING_CACHE[model]


def count_tokens_in_text(text: str, model: str = "gpt-4o") -> int:
    enc = _get_encoding(model)
    return len(enc.encode(text))


def count_tokens_from_messages(messages: List[Any], model: str = "gpt-4o") -> int:
    enc = _get_encoding(model)
    total_tokens = 0

    for message in messages:
        total_tokens += 4
        role = getattr(message, "type", "unknown")
        total_tokens += len(enc.encode(role))
        content = getattr(message, "content", "")
        if isinstance(content, str):
            total_tokens += len(enc.encode(content))
        elif isinstance(content, list):
            for block in content:
                if isinstance(block, dict) and block.get("type") == "text":
                    total_tokens += len(enc.encode(block.get("text", "")))
                elif isinstance(block, str):
                    total_tokens += len(enc.encode(block))

    total_tokens += 2
    return total_tokens
