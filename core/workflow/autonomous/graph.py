from langgraph.graph import StateGraph, START, END
from core.models.state import AgentState

def build_autonomous_graph(
    observer_agent,
    decider_agent,
    executor_agent,
    reflector_agent,
    recorder_agent,
    orchestrator,
) -> StateGraph:
    """
    Build the LangGraph for the Autonomous (AI-Driven) workflow.
    """
    graph = StateGraph(AgentState)

    # Define Nodes
    graph.add_node("orchestrator_node", orchestrator.orchestrate)
    graph.add_node("observer_node",     observer_agent.analyze)
    graph.add_node("decider_node",      decider_agent.decide)
    graph.add_node("executor_node",     executor_agent.execute)
    graph.add_node("reflector_node",    reflector_agent.evaluate)
    graph.add_node("recorder_node",     recorder_agent.record)

    # 1. START with the Judge
    graph.add_edge(START, "orchestrator_node")
    
    # 2. The Orchestrator DISPATCHES to a sub-agent
    # (Controlled via Command(goto=...) in the orchestrator_node itself)
    
    # 3. EVERY sub-agent MUST return only to the Orchestrator
    graph.add_edge("observer_node",  "orchestrator_node")
    graph.add_edge("decider_node",   "orchestrator_node")
    graph.add_edge("executor_node",  "orchestrator_node")
    graph.add_edge("reflector_node", "orchestrator_node")
    graph.add_edge("recorder_node",  "orchestrator_node")

    return graph.compile()
