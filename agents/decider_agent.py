from pydantic import BaseModel, Field
from langchain_core.messages import HumanMessage
from core.state import AgentState

class DeciderDecision(BaseModel):
    is_completed: bool = Field(description="True if the user's goal has been achieved")
    next_instruction: str = Field(
        description="Specific instruction for the Executor if not completed yet. "
                    "Example: 'Click the profile button at coordinates 100, 200'"
    )

class DeciderAgent:
    def __init__(self, llm):
        self.llm = llm.with_structured_output(DeciderDecision)

    def decide(self, state: AgentState) -> dict:
        prompt = (
            f"Final Goal: {state['task_goal']}\n"
            f"Screen Information: {state['observer_analysis']}\n"
            f"Action History: {state['action_history']}\n\n"
            f"TASK: Provide the next logical instruction to achieve the goal.\n\n"
            f"EXECUTOR CAPABILITIES:\n"
            f"- Can click/long-click coordinates (@x,y).\n"
            f"- Can type text.\n"
            f"- Can swipe/scroll the screen ('up', 'down', 'left', 'right'). USE THIS if the target is likely off-screen.\n"
            f"- Can start or stop specific apps using package names.\n"
            f"- Can press system buttons: back, home, enter.\n\n"
            f"RULES:\n"
            f"1. Always use @x,y coordinates provided in the Screen Information for click/long-click actions.\n"
            f"2. If the goal requires finding something not visible on the current screen, instruct the Executor to 'swipe_screen' in the appropriate direction.\n"
            f"3. If the goal is fully achieved, set is_completed to True.\n"
            f"4. Be specific and concise."
        )

        message = HumanMessage(content=prompt)
        decision = self.llm.invoke([message])

        status = "COMPLETED ✓" if decision.is_completed else f"Continuing → '{decision.next_instruction}'"
        print(f"[Decider] {status}")

        return {
            "is_completed": decision.is_completed,
            "decider_instruction": decision.next_instruction,
        }
