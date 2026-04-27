from typing import List, Optional, TypedDict

class AgentState(TypedDict):
    tcs_id: str
    navigation_context: str
    scenario_desc: str
    test_type: str
    user_role: str
    sub_steps: List[str]
    task_goal: str
    expected_result: str
    current_sub_step_index: int

    current_step: int
    screenshot_path: str
    previous_screenshot_path: str
    annotated_screenshot_path: str
    ui_elements_summary: str
    ocr_result: str
    detected_elements: str
    observer_analysis: str
    widgets: List[dict]
    
    action_plan: dict
    execution_result: str
    is_completed: bool
    
    action_history: List[dict]
    chat_logs: List[dict]
    orchestrator_reasoning: str
    sender: str
    next_agent: str
    stagnation_count: int          
    previous_ui_summary: str
    reflector_reasoning: str

    output_dir: str
    step_dir: str

    step_retry_count: int
    last_reflector_passed: bool

    figma_enabled: bool
    figma_start_node_id: str
    figma_end_node_id: str
    figma_end_screenshot_b64: str
    figma_bridge_steps: List[str]
    last_agent_calls: List[str]
    session_id: str
    start_time: float
    end_time: float
    recovery_attempts: int
