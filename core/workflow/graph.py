from langgraph.graph import StateGraph, START, END
from core.models.state import AgentState


def build_graph(observer_agent, decider_agent, executor_agent, supervisor_agent) -> StateGraph:
    graph = StateGraph(AgentState)

    graph.add_node("observer_node", observer_agent.analyze)
    graph.add_node("decider_node", decider_agent.decide)
    graph.add_node("executor_node", executor_agent.execute)
    graph.add_node("supervisor_node", supervisor_agent.evaluate)

    graph.add_edge(START, "observer_node")
    graph.add_edge("observer_node", "decider_node")
    graph.add_edge("decider_node", "executor_node")
    graph.add_edge("executor_node", "supervisor_node")

    graph.add_conditional_edges(
        "supervisor_node",
        lambda state: "end" if state.get("is_completed") or state.get("current_step", 0) >= 25 else "continue",
        {
            "continue": "observer_node",
            "end": END
        }
    )

    app = graph.compile()
    return app
