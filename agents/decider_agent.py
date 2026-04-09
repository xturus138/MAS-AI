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
            f"TASK: Provide an instruction to the Executor.\n"
            f"RULES: Use @x,y coordinates provided by the Observer. "
            f"DO NOT guess coordinates if they are not in the screen analysis."
        )

        message = HumanMessage(content=prompt)
        decision = self.llm.invoke([message])

        status = "COMPLETED ✓" if decision.is_completed else f"Continuing → '{decision.next_instruction}'"
        print(f"[Decider] {status}")

        return {
            "is_completed": decision.is_completed,
            "decider_instruction": decision.next_instruction,
        }
