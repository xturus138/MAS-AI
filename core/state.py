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
    action_plan: dict
    execution_result: str
    is_completed: bool
    action_history: List[str]