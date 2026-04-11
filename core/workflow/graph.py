from langgraph.graph import StateGraph, START, END
from core.models.state import AgentState


def build_graph(observer_agent, decider_agent, executor_agent) -> StateGraph:
    def route_after_decider(state: AgentState) -> str:
        if state["is_completed"]:
            print("\nWORKFLOW COMPLETED: Goal Reached")
            return END
        if state["current_step"] >= 25:
            print("\nWORKFLOW STOPPED: Maximum step budget reached (25 steps)")
            return END
        return "executor_node"

    graph = StateGraph(AgentState)

    graph.add_node("observer_node", observer_agent.analyze)
    graph.add_node("decider_node", decider_agent.decide)
    graph.add_node("executor_node", executor_agent.execute)

    graph.add_edge(START, "observer_node")
    graph.add_edge("observer_node", "decider_node")

    graph.add_conditional_edges(
        source="decider_node",
        path=route_after_decider,
        path_map={
            "executor_node": "executor_node",
            END: END,
        }
    )

    graph.add_edge("executor_node", "observer_node")

    app = graph.compile()
    return app
