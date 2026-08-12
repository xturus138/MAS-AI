from typing import List, Optional, TypedDict


class AgentState(TypedDict):
    session_id: str
    tcs_id: str
    sender: str
    next_agent: str
    current_step: int
    is_completed: bool

    screenshot_path: str
    output_dir: str
    step_dir: str
    output_paths: dict
    steps_dir: str
    logs_dir: str
    llm_logs_dir: str
    reports_dir: str
    figma_dir: str
    action_plan: dict
    execution_result: str
    last_reflector_passed: bool
    last_reflector_reasoning: str

    observer_analysis: str
    observer_analysis_step: int
    widgets: List[dict]
    observation_source: Optional[str]
    confidence_score: Optional[float]
    fallback_reason: Optional[str]

    memory_context: str

    current_sub_step_index: int
    orchestrator_instruction: str
    is_final_step: bool
    is_first_verify_attempt: bool
    step_retry_count: int

    stagnation_count: int
    recovery_attempts: int
    last_agent_calls: List[str]

    start_time: float
    end_time: float
    steps_completed_count: int
    total_reflector_calls: int
    reflector_pass_count: int
    total_first_verify_calls: int
    reflector_first_pass_count: int
    widget_lookup_success: int
    widget_lookup_fail: int
    widget_text_fallback_count: int

    uncertainty_artifact_dir: str
