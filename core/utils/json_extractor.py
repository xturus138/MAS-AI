"""Shared JSON extraction and recovery utilities for LLM structured output.



All agents that use structured LLM output (decider, reflector, orchestrator)

share the same patterns for recovering from malformed JSON. This module

consolidates those patterns into a single place.



Usage:

    from core.utils.json_extractor import extract_json_from_llm_output

    from core.utils.json_extractor import invoke_with_json_recovery

"""



import json

import time

from typing import Any, Callable, Optional, TypeVar



T = TypeVar("T")





def extract_json_from_llm_output(raw_output: str) -> Optional[Any]:

    """Safely extract JSON from LLM output that may contain XML tags or extra text.



    Attempts multiple strategies:

    1. Extract content from <thinking> tags and parse JSON within

    2. Find outermost JSON object via brace counting

    3. Look for JSON array format via bracket counting

    4. Return None if no valid JSON found

    """

    if not raw_output:

        return None



    cleaned = raw_output.strip()



    if "<thinking>" in cleaned and "</thinking>" in cleaned:

        start = cleaned.find("<thinking>")

        end = cleaned.find("</thinking>")

        if start != -1 and end != -1:

            inner = cleaned[start + len("<thinking>"):end].strip()

            try:

                return json.loads(inner)

            except json.JSONDecodeError:

                pass

            cleaned = inner



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

                candidate = cleaned[json_start:i + 1]

                try:

                    return json.loads(candidate)

                except json.JSONDecodeError:

                    continue



    if json_start == -1 and "[" in cleaned:

        bracket_depth = 0

        arr_start = -1

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

            if char == "[":

                if bracket_depth == 0:

                    arr_start = i

                bracket_depth += 1

            elif char == "]":

                bracket_depth -= 1

                if bracket_depth == 0 and arr_start != -1:

                    candidate = cleaned[arr_start:i + 1]

                    try:

                        return json.loads(candidate)

                    except json.JSONDecodeError:

                        continue



    return None





def _is_rate_limit_error(error: Exception) -> bool:

    """Check if an exception is a 429 rate-limit error."""

    err_str = str(error)

    return "429" in err_str or "rate" in err_str.lower() or "too many requests" in err_str.lower()





def _is_json_parse_error(error: Exception) -> bool:

    """Check if an exception is a JSON parsing error from structured output."""

    error_str = str(error)

    return (

        "json_invalid" in error_str

        or "Invalid JSON" in error_str

        or "missing" in error_str.lower()

    )





def invoke_with_json_recovery(

    structured_llm: Any,

    base_llm: Any,

    messages: list,

    model_factory: Callable[[dict], T],

    max_retries: int = 2,

    rate_limit_retries: int = 2,

) -> T:

    """Invoke structured LLM with automatic JSON extraction retry.



    Args:

        structured_llm: LLM client with .invoke() that returns structured output (Pydantic model).

        base_llm: Raw LLM client (without structured output wrapper) for fallback recovery.

        messages: List of messages to send.

        model_factory: Callable that takes a dict and returns a model instance.

            Used to reconstruct the model from recovered JSON.

        max_retries: Number of JSON recovery attempts (default 2).

        rate_limit_retries: Number of rate-limit retries (default 2).



    Returns:

        A model instance of type T.



    Raises:

        The last exception if all recovery attempts fail.

    """

    last_error = None

    rate_limit_backoff = 1.0



    for attempt in range(max_retries):

        try:

            result = structured_llm.invoke(messages)

            if result is not None:

                return result

            print(f"[JSON Extractor] Structured LLM returned None, attempting recovery...")

            last_error = Exception("Structured LLM returned None")

        except Exception as e:

            last_error = e



            if _is_rate_limit_error(e):

                if attempt < rate_limit_retries:

                    print(

                        f"[JSON Extractor] Rate limited (429), retrying in "

                        f"{rate_limit_backoff:.1f}s (attempt {attempt + 1})..."

                    )

                    time.sleep(rate_limit_backoff)

                    rate_limit_backoff = min(rate_limit_backoff * 2, 16.0)

                    continue

                break



            if not _is_json_parse_error(e):

                raise



            if attempt < max_retries - 1:

                try:

                    print(f"[JSON Extractor] Attempting JSON recovery (attempt {attempt + 1})...")

                    raw_response = base_llm.invoke(messages)

                    raw_text = (

                        raw_response.content

                        if hasattr(raw_response, "content")

                        else str(raw_response)

                    )



                    extracted = extract_json_from_llm_output(raw_text)

                    if extracted:

                        return model_factory(extracted)

                except Exception as inner_e:

                    print(f"[JSON Extractor] JSON recovery attempt {attempt + 1} failed: {inner_e}")



            if attempt < max_retries - 1:

                from langchain_core.messages import AIMessage



                reminder = AIMessage(

                    content=(

                        "IMPORTANT: Return ONLY a valid JSON object with ALL required fields. "

                        "No XML tags. No extra text."

                    )

                )

                messages = messages + [reminder]



    raise last_error

