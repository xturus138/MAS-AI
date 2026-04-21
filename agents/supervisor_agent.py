from pydantic import BaseModel, Field
from langchain_core.prompts import ChatPromptTemplate
from core.models.state import AgentState
from core.utils.toons_helper import compress_and_report

class EvaluationResult(BaseModel):
    is_completed: bool = Field(description="True if the overall goal is completed, otherwise False.")
    current_subgoal: str = Field(description="What needs to be done next.")
    reasoning: str = Field(description="Why this subgoal is necessary or why the task is complete.")

class SupervisorAgent:
    def __init__(self, llm):
        self.llm = llm.with_structured_output(EvaluationResult)
        self.prompt = ChatPromptTemplate.from_messages([
            ("system", "You are the Supervisor Agent in an Android GUI testing Swarm.\n"
                       "Your job is to evaluate the last execution, determine if the overall goal is completed, "
                       "and provide a concrete 'current_subgoal' for the next iteration."),
            ("human", "Goal: {task_goal}\n"
                      "Last Action Result: {execution_result}\n"
                      "Recent Actions: {history_json}\n\n"
                      "Evaluate and output the result.")
        ])

    def evaluate(self, state: AgentState) -> dict:
        history_window = list(state.get("action_history") or [])[-10:]
        history_json = compress_and_report(history_window, "action_history", "supervisor") if history_window else "[]"
        
        messages = self.prompt.format_messages(
            task_goal=state.get('task_goal'),
            execution_result=state.get('execution_result'),
            history_json=history_json
        )
        
        print("[Supervisor] Evaluating execution and determining next subgoal...")
        
        try:
            result = self.llm.invoke(
                messages,
                config={"tags": ["supervisor", f"step_{state.get('current_step', 0)}"]}
            )
            is_completed = result.is_completed
            current_subgoal = result.current_subgoal
            reasoning = result.reasoning
        except Exception as e:
            print(f"[Supervisor] Parser failed or chain failed: {e}. Defaulting to not completed.")
            is_completed = False
            current_subgoal = "Determine next action based on screen state."
            reasoning = f"Failed to parse supervisor output: {str(e)}"
            
        print(f"[Supervisor] Completed: {is_completed} | Subgoal: {current_subgoal}")
            
        execution_result = str(state.get("execution_result", ""))
        stagnation_count = state.get("stagnation_count", 0)
        
        if "ERROR" in execution_result.upper():
             stagnation_count += 1
        else:
             stagnation_count = 0
             
        return {
            "is_completed": is_completed,
            "current_subgoal": current_subgoal,
            "orchestrator_reasoning": reasoning,
            "stagnation_count": stagnation_count,
            "sender": "supervisor"
        }
