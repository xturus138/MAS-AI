import json
import os
import datetime
import re
from typing import Any, Dict, List, Optional
from langchain_core.callbacks import BaseCallbackHandler
from langchain_core.messages import messages_to_dict
from langchain_core.outputs import LLMResult
from core.utils.token_counter import count_tokens_from_messages, count_tokens_in_text
from core.utils.pricing import calculate_cost, get_model_pricing_info
from shared import config

_GREEN  = "\033[92m"
_YELLOW = "\033[93m"
_RED    = "\033[91m"
_CYAN   = "\033[96m"
_RESET  = "\033[0m"
_BOLD   = "\033[1m"


class SafeJSONEncoder(json.JSONEncoder):
    def default(self, obj):
        try:
            return super().default(obj)
        except TypeError:
            if hasattr(obj, "__name__"):
                return f"<class {obj.__name__}>"
            if hasattr(obj, "dict"):
                return obj.dict()
            if hasattr(obj, "model_dump"):
                return obj.model_dump()
            return str(obj)


class LLMJsonLogger(BaseCallbackHandler):
    def __init__(self, log_dir: str = "outputs/llm_logs", session_id: Optional[str] = None, model_name: str = "gpt-4o"):
        self.model_name = model_name
        self.log_dir = log_dir
        if session_id:
            self.log_dir = os.path.join(self.log_dir, session_id)
        if not os.path.exists(self.log_dir):
            os.makedirs(self.log_dir, exist_ok=True)

        self._pending: Dict[str, dict] = {}

    def _sanitize(self, filename: str) -> str:
        return re.sub(r'[<>:"/\\|?*]', "_", filename)

    def on_chat_model_start(
        self,
        serialized: Dict[str, Any],
        messages: List[List[Any]],
        *,
        run_id: Any,
        parent_run_id: Optional[Any] = None,
        tags: Optional[List[str]] = None,
        metadata: Optional[Dict[str, Any]] = None,
        **kwargs: Any,
    ) -> Any:
        agent_name = "unknown_agent"
        if tags:
            agent_tags = [t for t in tags if t in ["orchestrator", "decider", "observer", "reflector", "recorder"]]
            if agent_tags:
                agent_name = agent_tags[0]
            else:
                agent_name = tags[0]
        elif metadata and "agent" in metadata:
            agent_name = metadata["agent"]

        agent_name = self._sanitize(agent_name)

        for i, message_list in enumerate(messages):
            timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S_%f")
            filename  = f"{agent_name}_{timestamp}_{i}.json"
            filepath  = os.path.join(self.log_dir, filename)

            prompt_tokens = count_tokens_from_messages(message_list, model=self.model_name)
            usage_ratio   = prompt_tokens / config.TOKEN_CONTEXT_WINDOW

            if usage_ratio >= 1.0:
                color   = _RED
                warning = f" {_BOLD}[!! OVER LIMIT]{_RESET}{_RED}"
            elif usage_ratio >= config.TOKEN_WARN_THRESHOLD:
                color   = _YELLOW
                warning = f" {_BOLD}[! HIGH USAGE]{_RESET}{_YELLOW}"
            else:
                color   = _GREEN
                warning = ""

            print(
                f"{_CYAN}[Token Tracker]{_RESET} "
                f"{_BOLD}{agent_name.upper()}{_RESET} | "
                f"Prompt Tokens: "
                f"{color}{prompt_tokens:,}{_RESET}"
                f"{color}{warning}{_RESET}"
            )

            log_data = {
                "agent":                agent_name,
                "model":                self.model_name,
                "timestamp":            timestamp,
                "prompt_tokens":        prompt_tokens,
                "completion_tokens":    0,
                "total_tokens":         prompt_tokens,
                "cost_usd":             0.0,
                "pricing_info":         get_model_pricing_info(self.model_name),
                "messages":             messages_to_dict(message_list),
                "metadata":             metadata or {},
                "tags":                 tags or [],
                "kwargs":               kwargs,
            }

            try:
                with open(filepath, "w", encoding="utf-8") as f:
                    json.dump(log_data, f, indent=2, ensure_ascii=False, cls=SafeJSONEncoder)
            except Exception as e:
                print(f"[!] Failed to log LLM payload: {e}")

            pending_key = f"{run_id}_{i}"
            self._pending[pending_key] = {
                "filepath":      filepath,
                "prompt_tokens": prompt_tokens,
            }

    def on_llm_end(
        self,
        response: LLMResult,
        *,
        run_id: Any,
        parent_run_id: Optional[Any] = None,
        **kwargs: Any,
    ) -> Any:
        """
        Fired after the LLM returns. We use this to:
        1. Extract actual completion tokens (from usage_metadata if available,
           otherwise estimate from the response text).
        2. Calculate per-call cost using the pricing table.
        3. Patch the previously written log JSON file with the final numbers.
        """
        for i, generation_list in enumerate(response.generations):
            pending_key = f"{run_id}_{i}"
            pending = self._pending.pop(pending_key, None)
            if pending is None:
                continue

            filepath     = pending["filepath"]
            prompt_tokens = pending["prompt_tokens"]

            completion_tokens = 0
            llm_output = response.llm_output or {}

            usage = llm_output.get("token_usage") or llm_output.get("usage") or {}
            if usage:
                completion_tokens = (
                    usage.get("completion_tokens")
                    or usage.get("output_tokens")
                    or 0
                )
                api_prompt = usage.get("prompt_tokens") or usage.get("input_tokens")
                if api_prompt:
                    prompt_tokens = api_prompt

            if completion_tokens == 0:
                for gen in generation_list:
                    text = getattr(gen, "text", "") or ""
                    if not text and hasattr(gen, "message"):
                        text = getattr(gen.message, "content", "") or ""
                    completion_tokens += count_tokens_in_text(text, model=self.model_name)

            total_tokens = prompt_tokens + completion_tokens
            cost_usd     = calculate_cost(self.model_name, prompt_tokens, completion_tokens)

            print(
                f"{_CYAN}[Cost Tracker]{_RESET} "
                f"{_BOLD}{os.path.basename(filepath).split('_')[0].upper()}{_RESET} | "
                f"Completion: {_GREEN}{completion_tokens:,} tokens{_RESET} | "
                f"Total: {_BOLD}{total_tokens:,}{_RESET} | "
                f"Cost: {_YELLOW}${cost_usd:.6f}{_RESET}"
            )

            try:
                with open(filepath, "r", encoding="utf-8") as f:
                    log_data = json.load(f)

                log_data["prompt_tokens"]     = prompt_tokens
                log_data["completion_tokens"] = completion_tokens
                log_data["total_tokens"]      = total_tokens
                log_data["cost_usd"]          = cost_usd

                with open(filepath, "w", encoding="utf-8") as f:
                    json.dump(log_data, f, indent=2, ensure_ascii=False, cls=SafeJSONEncoder)
            except Exception as e:
                print(f"[!] Failed to update cost in log: {e}")
