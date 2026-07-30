from langgraph.graph import StateGraph, START, END
from langgraph.prebuilt import ToolNode

from .state import AgentState
from .tools import get_tools
from .nodes import agent_node, should_continue, execute_node

def create_agent_graph():
    workflow = StateGraph(AgentState)
    
    # Add nodes
    workflow.add_node("agent", agent_node)
    workflow.add_node("tools", ToolNode(get_tools()))
    workflow.add_node("execute_node", execute_node)

    # Add edges
    workflow.add_edge(START, "agent")
    workflow.add_conditional_edges("agent", should_continue, {"tools": "tools", "execute_node": "execute_node", END: END})
    workflow.add_edge("tools", "agent")
    
    def route_execution(state: AgentState):
        if state.get("execution_success"):
            return END
        return "agent"
        
    workflow.add_conditional_edges("execute_node", route_execution, {END: END, "agent": "agent"})

    return workflow.compile()
