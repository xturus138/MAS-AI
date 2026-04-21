from abc import ABC, abstractmethod
from typing import Any, List, Optional

class ILLMClient(ABC):
    @abstractmethod
    def invoke(self, messages: List[Any], **kwargs) -> Any:
        """Invoke the LLM with a list of messages."""
        pass

    @abstractmethod
    def with_structured_output(self, schema: Any) -> Any:
        """Return an LLM instance that produces structured output."""
        pass

    @abstractmethod
    def stream(self, messages: List[Any], **kwargs) -> Any:
        """Stream the LLM response."""
        pass
