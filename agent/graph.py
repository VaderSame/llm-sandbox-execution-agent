from langgraph.graph import StateGraph, START, END
from langgraph.prebuilt import ToolNode

from .state import AgentState
from .tools import get_tools
from .nodes import user_input_node, agent_node, debugger_node, execute_node

def create_agent_graph():
    workflow = StateGraph(AgentState)
    
    # Add nodes
    workflow.add_node("user_input", user_input_node)
    workflow.add_node("agent", agent_node)
    workflow.add_node("debugger", debugger_node)
    workflow.add_node("agent_tools", ToolNode(get_tools()))
    workflow.add_node("debugger_tools", ToolNode(get_tools()))
    workflow.add_node("execute_node", execute_node)

    # Add edges
    workflow.add_edge(START, "user_input")
    workflow.add_edge("user_input", "agent")
    
    def agent_should_continue(state: AgentState):
        messages = state["messages"]
        last_message = messages[-1]
        if hasattr(last_message, "tool_calls") and last_message.tool_calls:
            if any(tc["name"] == "submit_for_execution" for tc in last_message.tool_calls):
                return "execute_node"
            return "agent_tools"
        return END

    workflow.add_conditional_edges("agent", agent_should_continue, {"agent_tools": "agent_tools", "execute_node": "execute_node", END: END})
    workflow.add_edge("agent_tools", "agent")
    
    def route_execution(state: AgentState):
        if state.get("execution_success"):
            return END
        return "debugger"
        
    workflow.add_conditional_edges("execute_node", route_execution, {END: END, "debugger": "debugger"})
    
    def debugger_should_continue(state: AgentState):
        messages = state["messages"]
        
        last_message = messages[-1]
        if hasattr(last_message, "tool_calls") and last_message.tool_calls:
            if any(tc["name"] == "submit_for_execution" for tc in last_message.tool_calls):
                return "execute_node"
            return "debugger_tools"
        return END

    workflow.add_conditional_edges("debugger", debugger_should_continue, {"debugger_tools": "debugger_tools", "execute_node": "execute_node", END: END})
    workflow.add_edge("debugger_tools", "debugger")

    # Compile the workflow
    app = workflow.compile()
    
    # --- Generate and save the Mermaid graph as a PNG ---
    try:
        with open("agent_graph.png", "wb") as f:
            f.write(app.get_graph().draw_mermaid_png())
    except Exception as e:
        print(f"Failed to save graph image: {e}")

    return app
