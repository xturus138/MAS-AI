class MASError(Exception):
    pass


class PerceptionError(MASError):
    pass


class ScreenshotError(PerceptionError):
    pass


class OCRError(PerceptionError):
    pass


class CVDetectionError(PerceptionError):
    pass


class AnnotationError(PerceptionError):
    pass


class PerceptionTimeoutError(PerceptionError):
    pass


class ToolExecutionError(MASError):
    def __init__(self, tool_name: str, reason: str):
        self.tool_name = tool_name
        self.reason = reason
        super().__init__(f"Tool '{tool_name}' failed: {reason}")


class AgentError(MASError):
    pass


class AgentStagnationError(AgentError):
    def __init__(self, agent: str, count: int):
        self.agent = agent
        self.count = count
        super().__init__(f"Agent '{agent}' stagnated for {count} consecutive steps.")


class LLMError(AgentError):
    pass


class LLMTimeoutError(LLMError):
    pass


class LLMResponseParseError(LLMError):
    pass


class FigmaError(MASError):
    pass


class FigmaConnectionError(FigmaError):
    pass


class FigmaNodeNotFoundError(FigmaError):
    def __init__(self, node_id: str):
        self.node_id = node_id
        super().__init__(f"Figma node not found: {node_id}")


class WorkflowError(MASError):
    pass


class StepLimitExceededError(WorkflowError):
    def __init__(self, max_steps: int):
        self.max_steps = max_steps
        super().__init__(f"Workflow exceeded maximum step limit of {max_steps}.")


class RecoveryLimitExceededError(WorkflowError):
    def __init__(self, max_attempts: int):
        self.max_attempts = max_attempts
        super().__init__(f"Recovery attempts exhausted after {max_attempts} tries.")
