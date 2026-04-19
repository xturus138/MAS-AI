from typing import List, TypedDict


class AgentState(TypedDict):
    task_goal: str
    current_step: int
    screenshot_path: str
    annotated_screenshot_path: str
    ui_elements_summary: str
    ocr_result: str
    detected_elements: str
    observer_analysis: str
    widgets: List[dict]
    action_plan: dict
    execution_result: str
    is_completed: bool
    action_history: List[str]
    current_subgoal: str
    orchestrator_reasoning: str
    sender: str
    stagnation_count: int          
    previous_ui_summary: str       