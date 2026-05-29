from typing import List, Optional, TypedDict


class AgentState(TypedDict):
    # ── Control signals ───────────────────────────────────────────────────────
    session_id: str
    tcs_id: str
    sender: str
    next_agent: str
    current_step: int
    is_completed: bool

    # ── Current-step working memory ───────────────────────────────────────────
    screenshot_path: str
    output_dir: str
    step_dir: str
    action_plan: dict
    execution_result: str
    last_reflector_passed: bool

    # ── Current observer output (live, not persisted across steps) ────────────
    observer_analysis: str
    observer_analysis_step: int     # current_step when observer last ran (staleness check)
    widgets: List[dict]

    # ── MIRIX: retrieved memory context injected into every agent prompt ───────
    memory_context: str

    # ── Orchestrator control ──────────────────────────────────────────────────
    current_sub_step_index: int
    orchestrator_instruction: str   # instruction set by autonomous orchestrator for current step
    is_final_step: bool             # set by orchestrator when dispatching VERIFY for the final goal
    is_first_verify_attempt: bool   # set by orchestrator before each reflector dispatch
    step_retry_count: int

    # ── Stagnation / recovery ─────────────────────────────────────────────────
    stagnation_count: int
    recovery_attempts: int
    last_agent_calls: List[str]

    # ── Research metrics counters ─────────────────────────────────────────────
    start_time: float
    end_time: float
    steps_completed_count: int          # incremented whenever reflector passed=True and system advances
    total_reflector_calls: int
    reflector_pass_count: int
    total_first_verify_calls: int
    reflector_first_pass_count: int
    widget_lookup_success: int
    widget_lookup_fail: int
