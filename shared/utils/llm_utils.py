"""
Shared LLM utility functions for MAS AI agents.

Centralises duplicated helpers that previously lived in
decider_agent.py, reflector_agent.py, and the predefined orchestrator.
"""

import base64
import json
from typing import Optional

import cv2


def encode_image(image_path: str, max_height: int = 720) -> str:
    """Resize and encode an image to base64 WebP (JPEG fallback).

    Shared by ObserverAgent and ReflectorAgent to avoid duplication.
    """
    img = cv2.imread(image_path)
    if img is None:
        return ""

    h, w = img.shape[:2]
    if h > max_height:
        scale = max_height / h
        new_w = int(w * scale)
        img = cv2.resize(img, (new_w, max_height), interpolation=cv2.INTER_AREA)

    success, buffer = cv2.imencode(".webp", img, [int(cv2.IMWRITE_WEBP_QUALITY), 70])
    if not success:
        success, buffer = cv2.imencode(".jpg", img, [int(cv2.IMWRITE_JPEG_QUALITY), 75])
    if not success:
        return ""

    return base64.b64encode(buffer).decode("utf-8")


def extract_json_str_from_llm_output(raw_output: str) -> Optional[str]:
    """Extract a JSON string from LLM output that may contain XML tags or extra prose.

    Tries three strategies in order:
    1. Content inside <thinking>…</thinking> tags.
    2. First complete JSON object found via brace-matching.
    3. First complete JSON array found via bracket-matching.

    Returns the extracted JSON *string* (not parsed), or None if nothing valid found.
    Used by agents that feed the string into a Pydantic parser or json.loads().
    """
    if not raw_output:
        return None

    cleaned = raw_output.strip()

    # Strategy 1: content inside <thinking> tags
    if "<thinking>" in cleaned and "</thinking>" in cleaned:
        start = cleaned.find("<thinking>")
        end = cleaned.find("</thinking>")
        if start != -1 and end != -1:
            inner = cleaned[start + len("<thinking>") : end].strip()
            try:
                json.loads(inner)
                return inner
            except json.JSONDecodeError:
                pass
            cleaned = inner

    # Strategy 2: first complete JSON object
    brace_depth = 0
    json_start = -1
    in_string = False
    escape_next = False

    for i, char in enumerate(cleaned):
        if escape_next:
            escape_next = False
            continue
        if char == "\\":
            escape_next = True
            continue
        if char == '"' and not escape_next:
            in_string = not in_string
            continue
        if in_string:
            continue

        if char == "{":
            if brace_depth == 0:
                json_start = i
            brace_depth += 1
        elif char == "}":
            brace_depth -= 1
            if brace_depth == 0 and json_start != -1:
                candidate = cleaned[json_start : i + 1]
                try:
                    json.loads(candidate)
                    return candidate
                except json.JSONDecodeError:
                    continue

    # Strategy 3: first complete JSON array
    if json_start == -1 and "[" in cleaned:
        bracket_depth = 0
        arr_start = -1
        in_string = False
        for i, char in enumerate(cleaned):
            if char == '"':
                in_string = not in_string
                continue
            if in_string:
                continue
            if char == "[":
                if bracket_depth == 0:
                    arr_start = i
                bracket_depth += 1
            elif char == "]":
                bracket_depth -= 1
                if bracket_depth == 0 and arr_start != -1:
                    candidate = cleaned[arr_start : i + 1]
                    try:
                        json.loads(candidate)
                        return candidate
                    except json.JSONDecodeError:
                        continue

    return None


def parse_json_from_llm_output(raw_output: str) -> Optional[dict]:
    """Extract and *parse* a JSON object from LLM output.

    Returns the parsed dict/list, or None if no valid JSON found.
    Used by orchestrators that need the parsed structure directly.
    """
    json_str = extract_json_str_from_llm_output(raw_output)
    if json_str is None:
        return None
    try:
        return json.loads(json_str)
    except json.JSONDecodeError:
        return None
