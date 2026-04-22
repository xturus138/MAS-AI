import json
import os
import datetime
import re
from typing import Any, Dict, List, Optional
from langchain_core.callbacks import BaseCallbackHandler
from langchain_core.messages import messages_to_dict
from core.utils.token_counter import count_tokens_from_messages
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

            token_count = count_tokens_from_messages(message_list, model=self.model_name)
            usage_ratio = token_count / config.TOKEN_CONTEXT_WINDOW

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
                f"Total Prompt Estimate: "
                f"{color}{token_count:,} tokens{_RESET}"
                f"{color}{warning}{_RESET}"
            )

            log_data = {
                "agent":               agent_name,
                "timestamp":           timestamp,
                "token_count_estimate": token_count,
                "messages":            messages_to_dict(message_list),
                "metadata":            metadata or {},
                "tags":                tags or [],
                "kwargs":              kwargs
            }

            try:
                with open(filepath, "w", encoding="utf-8") as f:
                    json.dump(log_data, f, indent=2, ensure_ascii=False, cls=SafeJSONEncoder)
            except Exception as e:
                print(f"[!] Failed to log LLM payload: {e}")
