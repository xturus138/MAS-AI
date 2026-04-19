from langgraph.graph import StateGraph, START, END
from core.models.state import AgentState


def build_graph(orchestrator_agent, observer_agent, decider_agent, executor_agent) -> StateGraph:
    graph = StateGraph(AgentState)

    graph.add_node("orchestrator_node", orchestrator_agent.route)
    graph.add_node("observer_node",     observer_agent.analyze)
    graph.add_node("decider_node",      decider_agent.decide)
    graph.add_node("executor_node",     executor_agent.execute)

    graph.add_edge(START, "orchestrator_node")

    app = graph.compile()
    return app
