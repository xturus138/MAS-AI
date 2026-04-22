from langgraph.graph import StateGraph, START, END
from core.models.state import AgentState

def next_step_or_end(state: AgentState) -> str:
    if state.get("is_completed", False):
        return END
    return "observer_node"

def build_graph(observer_agent, decider_agent, executor_agent, reflector_agent, recorder_agent, orchestrator_agent) -> StateGraph:
    graph = StateGraph(AgentState)

    graph.add_node("orchestrator_node", orchestrator_agent.orchestrate)
    graph.add_node("observer_node", observer_agent.analyze)
    graph.add_node("decider_node", decider_agent.decide)
    graph.add_node("executor_node", executor_agent.execute)
    graph.add_node("reflector_node", reflector_agent.evaluate)
    graph.add_node("recorder_node", recorder_agent.record)

    graph.add_edge(START, "orchestrator_node")
    
    graph.add_conditional_edges(
        "orchestrator_node",
        next_step_or_end
    )
    
    graph.add_edge("observer_node", "decider_node")
    graph.add_edge("decider_node", "executor_node")
    graph.add_edge("executor_node", "reflector_node")
    graph.add_edge("reflector_node", "recorder_node")
    graph.add_edge("recorder_node", "orchestrator_node")

    app = graph.compile()
    return app
