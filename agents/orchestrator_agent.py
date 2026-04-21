from langchain_core.messages import SystemMessage, HumanMessage
from langgraph.types import Command
from core.models.state import AgentState
import json, re
from core.utils.toons_helper import compress_and_report

SYSTEM_PROMPT = """You are the Orchestrator in an Android GUI testing Multi-Agent Swarm.

You are the strategic router. You do NOT perform UI actions.
Decide which sub-agent to call next based on the current state.

Sub-agents:
  - observer  : Takes a fresh screenshot and analyses the screen.
  - decider   : Receives a 'current_subgoal' from you and produces an ActionPlan.
  - executor  : Executes the ActionPlan that the Decider prepared.
  - END       : Use when the goal is fully achieved.

Routing Rules:
- is_completed=true -> END.
- current_step > 25 -> END (safety limit).
- START or executor done -> observer.
- observer done -> decider (with a concrete subgoal).
- decider done -> executor.
- UI stuck/looping -> new subgoal or press back.

Output ONE JSON object:
{"next": "observer"|"decider"|"executor"|"END", "current_subgoal": "...", "reasoning": "..."}
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

        # Compress action history with TOONS — uniform dict keys enable tabular compression.
        history_window = list(state.get("action_history") or [])[-10:]
        history_json = compress_and_report(history_window, "action_history", "orchestrator") if history_window else "[]"
        sender = state.get("sender", "START")

        # Extract only the SUMMARY line from observer_analysis to minimize token usage.
        # The full semantic map is for the Decider; the Orchestrator only needs high-level context.
        raw_analysis = state.get("observer_analysis", "None")
        summary_match = re.search(r"SUMMARY:\s*(.+)", raw_analysis, re.DOTALL)
        screen_summary = summary_match.group(1).strip() if summary_match else raw_analysis[:300]

        human_prompt = (
            f"Goal: {state.get('task_goal')}\n"
            f"Step: {state.get('current_step')} | Last Agent: {sender} | Stagnation: {state.get('stagnation_count', 0)}\n"
            f"Screen Summary: {screen_summary}\n"
            f"Execution Result: {state.get('execution_result', 'N/A')}\n"
            f"Recent Actions: {history_json}\n\n"
            f"Decide the NEXT agent. Output ONE JSON object."
        )

        messages = [
            SystemMessage(content=SYSTEM_PROMPT),
            HumanMessage(content=human_prompt),
        ]

        print(f"[Orchestrator] Dynamically evaluating transition from {sender}...")

        # Enforce observer as the first move to gain context
        if sender == "START":
            return Command(
                goto="observer_node",
                update={
                    "current_subgoal": "Capture initial screen state.",
                    "orchestrator_reasoning": "Initial state requires observation.",
                    "sender": "orchestrator"
                }
            )

        response = self.llm.invoke(
            messages, 
            config={"tags": ["orchestrator", f"step_{state.get('current_step', 0)}"]}
        )

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
