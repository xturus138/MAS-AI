from langgraph.graph import StateGraph, START, END
from core.models.state import AgentState


def build_autonomous_graph(
    observer_agent,
    decider_agent,
    executor_agent,
    reflector_agent,
    orchestrator,
) -> StateGraph:
    """
    Build the LangGraph for the Autonomous (AI-Driven) workflow.

    With MIRIX, RecorderAgent is removed from the mid-cycle loop.
    Recording happens once after the graph exits, via recorder.finalize_run_metrics().

    The orchestrator dispatches to sub-agents via Command(goto=...).
    Every sub-agent returns to the orchestrator node via static edges.
    """
    graph = StateGraph(AgentState)

    graph.add_node("orchestrator_node", orchestrator.orchestrate)
    graph.add_node("observer_node",     observer_agent.analyze)
    graph.add_node("decider_node",      decider_agent.decide)
    graph.add_node("executor_node",     executor_agent.execute)
    graph.add_node("reflector_node",    reflector_agent.evaluate)

    graph.add_edge(START, "orchestrator_node")

    # Every sub-agent returns to the orchestrator for the next judgment
    graph.add_edge("observer_node",  "orchestrator_node")
    graph.add_edge("decider_node",   "orchestrator_node")
    graph.add_edge("executor_node",  "orchestrator_node")
    graph.add_edge("reflector_node", "orchestrator_node")

    return graph.compile()
