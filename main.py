import os
import sys
import argparse
from dotenv import load_dotenv
from langchain_core.messages import HumanMessage
from agent import create_agent_graph

load_dotenv()

def main():
    parser = argparse.ArgumentParser(description="Run the Execution Agent on a workspace.")
    parser.add_argument("workspace_path", nargs='?', default=".", type=str, help="The absolute path to the workspace directory (defaults to current directory).")
    parser.add_argument("-i", "--interactive", action="store_true", help="Enable interactive mode for file writes.")
    args = parser.parse_args()
    
    if args.interactive:
        os.environ["INTERACTIVE_MODE"] = "1"
        print("Interactive mode enabled: You will be prompted before the agent edits files.")
    
    workspace_path = os.path.abspath(args.workspace_path)
    
    if not os.path.isdir(workspace_path):
        print(f"Error: {workspace_path} is not a valid directory.")
        sys.exit(1)
        
    app = create_agent_graph()
    
    initial_state = {
        "workspace_path": workspace_path,
        "messages": [],
        "repo_path": None,
        "execution_command": None
    }
    
    # Run the graph
    for event in app.stream(initial_state):
        for key, value in event.items():
            if key == "agent":
                message = value.get("messages", [None])[0]
                if message and hasattr(message, "tool_calls") and message.tool_calls:
                    print(f"Agent executing tools: {[tc['name'] for tc in message.tool_calls]}")
                else:
                    print("Agent responded.")
            elif key == "tools":
                pass
            elif key == "execute_node":
                pass

if __name__ == "__main__":
    main()
