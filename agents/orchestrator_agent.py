from langchain_core.messages import SystemMessage, HumanMessage
from langgraph.types import Command
from core.models.state import AgentState
import json, re

SYSTEM_PROMPT = """You are the Orchestrator Agent in an Android GUI testing Multi-Agent Swarm.

You are the strategic manager and central router. You do NOT perform any UI actions yourself.
Your only job is to evaluate the current state and decide which sub-agent should act next based on the full conversation history.

Sub-agents available:
  - observer  : Takes a fresh screenshot and analyses the screen when you need up-to-date UI info.
  - decider   : Receives a 'current_subgoal' from you and produces an ActionPlan.
  - executor  : Executes the ActionPlan that the Decider prepared.
  - END       : Use this when the goal is fully achieved.

TYPICAL WORKFLOW (but you are dynamic):
1. START or EXECUTOR just finished -> Call 'observer' to see what happened.
2. OBSERVER just finished -> Call 'decider' and set a 'current_subgoal'.
3. DECIDER just finished -> Call 'executor' to perform the action.
4. UI is stuck/looping -> Update 'current_subgoal' to try a different approach or press back.

Routing Rules:
- If 'is_completed' is true, route to 'END'.
- If 'current_step' > 25, route to 'END' (safety limit).
- You MUST provide a concrete 'current_subgoal' whenever routing to 'decider'.

Your output MUST be a single JSON object:
{
  "next": "observer" | "decider" | "executor" | "END",
  "current_subgoal": "Description of the next tactical objective",
  "reasoning": "Brief explanation of why this transition is necessary"
}
Output ONLY raw JSON."""

class OrchestratorAgent:
    def __init__(self, llm):
        self.llm = llm

    def route(self, state: AgentState) -> Command:
        # Safety bounds
        if state.get("is_completed"):
            print("[Orchestrator] Goal achieved. Ending.")
            return Command(goto="__end__", update={"sender": "orchestrator"})
        if state.get("current_step", 0) >= 25:
            print("[Orchestrator] Budget exceeded. Ending.")
            return Command(goto="__end__", update={"sender": "orchestrator"})

        history_text = "\n".join(state.get("action_history") or []) or "None"
        sender = state.get("sender", "START")

        human_prompt = (
            f"Goal: {state.get('task_goal')}\n"
            f"Current Step: {state.get('current_step')}\n"
            f"Last Agent (Sender): {sender}\n"
            f"Action History:\n{history_text}\n\n"
            f"Observer Perception (Full UI Map):\n{state.get('observer_analysis', 'None')}\n\n"
            f"Execution Result: {state.get('execution_result', 'N/A')}\n"
            f"Stagnation Count: {state.get('stagnation_count', 0)}\n\n"
            f"Task: Decide the NEXT agent to call. Use the Full UI Map to provide a highly specific subgoal if routing to the decider. Output ONE JSON object."
        )

        messages = [
            SystemMessage(content=SYSTEM_PROMPT),
            HumanMessage(content=human_prompt),
        ]

        print(f"[Orchestrator] Dynamically evaluating transition from {sender}...")
        response = self.llm.invoke(messages)

        raw = response.content.strip()
        raw = re.sub(r"^```(?:json)?", "", raw).strip()
        raw = re.sub(r"```$", "", raw).strip()

        try:
            parsed = json.loads(raw)
            next_node = str(parsed.get("next", "observer")).strip().lower()
            subgoal   = str(parsed.get("current_subgoal", "")).strip()
            reasoning = str(parsed.get("reasoning", "")).strip()
        except:
            print("[Orchestrator] Parser failed. Defaulting to observer.")
            next_node = "observer"
            subgoal = ""
            reasoning = "Unparseable LLM output."

        mapping = {
            "observer": "observer_node",
            "decider": "decider_node",
            "executor": "executor_node",
            "end": "__end__"
        }
        target = mapping.get(next_node, "observer_node")

        print(f"[Orchestrator] -> {target} | Subgoal: {subgoal} | Reason: {reasoning}")
        return Command(
            goto=target,
            update={
                "current_subgoal": subgoal,
                "orchestrator_reasoning": reasoning,
                "sender": "orchestrator",
                "action_plan": state.get("action_plan", {}) if target == "executor_node" else {}
            }
        )
