from langgraph.graph import StateGraph, START, END
from core.models.state import AgentState


def _next_step_or_end(state: AgentState) -> str:
    if state.get("is_completed", False):
        return END
    return "observer_node"


def build_predefined_graph(
    observer_agent,
    decider_agent,
    executor_agent,
    reflector_agent,
    orchestrator,
) -> StateGraph:
    """
    Build the LangGraph state machine for the Predefined (Scenario-Based) workflow.

    With MIRIX, RecorderAgent is removed from the mid-cycle loop.
    Recording happens once after the graph exits, via recorder.finalize_run_metrics().

    Loop:  START → orchestrator → observer → decider → executor → reflector → orchestrator → ...
    Exit:  orchestrator → END  (when is_completed=True)
    """
    graph = StateGraph(AgentState)

    graph.add_node("orchestrator_node", orchestrator.orchestrate)
    graph.add_node("observer_node",     observer_agent.analyze)
    graph.add_node("decider_node",      decider_agent.decide)
    graph.add_node("executor_node",     executor_agent.execute)
    graph.add_node("reflector_node",    reflector_agent.evaluate)

    graph.add_edge(START, "orchestrator_node")
    graph.add_conditional_edges("orchestrator_node", _next_step_or_end)

    graph.add_edge("observer_node",  "decider_node")
    graph.add_edge("decider_node",   "executor_node")
    graph.add_edge("executor_node",  "reflector_node")
    graph.add_edge("reflector_node", "orchestrator_node")

    return graph.compile()
