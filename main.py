import os
import sys
import argparse
from dotenv import load_dotenv
from langchain_core.messages import HumanMessage
from agent import create_agent_graph

load_dotenv()

def main():
    parser = argparse.ArgumentParser(description="Run the Execution Agent on a repository.")
    parser.add_argument("repo_path", type=str, help="The absolute path to the repository directory to execute.")
    parser.add_argument("--query", type=str, default="Please find and execute the main script in the repository.",
                        help="Optional initial instruction to the agent regarding parameters or execution mode.")
    args = parser.parse_args()
    
    repo_path = os.path.abspath(args.repo_path)
    
    if not os.path.isdir(repo_path):
        print(f"Error: {repo_path} is not a valid directory.")
        sys.exit(1)
        
    print(f"Starting execution agent for repository: {repo_path}")
    if args.query != "Please find and execute the main script in the repository.":
        print(f"Initial query: {args.query}")
        
    app = create_agent_graph()
    
    initial_state = {
        "messages": [HumanMessage(content=args.query)],
        "repo_path": repo_path,
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
