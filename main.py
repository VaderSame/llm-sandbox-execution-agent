import os
import sys
import argparse
from dotenv import load_dotenv
from langchain_core.messages import HumanMessage
from agent import create_agent_graph

load_dotenv()

def main():
    parser = argparse.ArgumentParser(description="Run the Execution Agent via CLI.")
    parser.add_argument("repo_name", nargs='?', type=str, help="The name of the repository inside the code_repo directory.")
    parser.add_argument("--query", type=str, default="Please execute the main script. If it fails, fix the code.", help="Custom instruction for the agent.")
    args = parser.parse_args()
    
    base_repo_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "code_repo"))
    
    # If no repo provided, list available ones and prompt user
    if not args.repo_name:
        if not os.path.exists(base_repo_dir):
            print(f"Error: {base_repo_dir} does not exist.")
            sys.exit(1)
            
        repos = [d for d in os.listdir(base_repo_dir) if os.path.isdir(os.path.join(base_repo_dir, d))]
        if not repos:
            print(f"No repositories found in {base_repo_dir}")
            sys.exit(1)
            
        print("Available repositories in code_repo:")
        for i, repo in enumerate(repos, 1):
            print(f"  {i}. {repo}")
            
        while True:
            try:
                choice = input("\nSelect a repository to execute (number or name): ").strip()
                if choice.isdigit() and 1 <= int(choice) <= len(repos):
                    args.repo_name = repos[int(choice)-1]
                    break
                elif choice in repos:
                    args.repo_name = choice
                    break
                else:
                    print("Invalid selection. Please try again.")
            except KeyboardInterrupt:
                print("\nExiting.")
                sys.exit(0)
                
    repo_path = os.path.join(base_repo_dir, args.repo_name)
    
    if not os.path.exists(repo_path):
        print(f"Error: {repo_path} is not a valid directory.")
        sys.exit(1)
        
    app = create_agent_graph()
    
    initial_state = {
        "repo_path": repo_path,
        "messages": [HumanMessage(content=args.query)]
    }
    
    def emit_event(event_type: str, payload: dict):
        if event_type == "agent_turn":
            print(f"\nAgent (Node: {payload.get('node')}):")
            if payload.get('content'):
                print(f"Thought: {payload.get('content')}")
            for tc in payload.get('tool_calls', []):
                print(f"Calling Tool: {tc.get('name')} with args: {tc.get('args')}")
        elif event_type == "sandbox_output":
            stream = payload.get("stream", "stdout")
            chunk = payload.get("chunk", "")
            if stream == "stdout":
                sys.stdout.write(chunk)
            else:
                sys.stderr.write(chunk)
            sys.stdout.flush()
        elif event_type == "execution_result":
            print(f"\nExecution finished (Success: {payload.get('success')})")
        elif event_type == "job_failed":
            print(f"\nJob Failed: {payload.get('error')}")
            
    config = {
        "configurable": {
            "thread_id": "cli_session", 
            "emit_event": emit_event
        }
    }
    
    print(f"Starting execution for {args.repo_name}...\n")
    
    is_resume = False
    resume_data = None
    
    while True:
        try:
            if not is_resume:
                stream = app.stream(initial_state, config=config)
            else:
                stream = app.stream(Command(resume=resume_data), config=config)
                
            for event in stream:
                # We extract the same messages logic here as server.py
                for node_name, node_state in event.items():
                    messages = node_state.get("messages", [])
                    if messages:
                        last_msg = messages[-1]
                        if node_name in ["agent", "debugger"]:
                            tool_calls = getattr(last_msg, "tool_calls", [])
                            emit_event("agent_turn", {
                                "node": node_name,
                                "content": last_msg.content,
                                "tool_calls": tool_calls
                            })
                        elif node_name in ["agent_tools", "debugger_tools"]:
                            emit_event("tool_result", {
                                "tool_name": last_msg.name,
                                "result": last_msg.content
                            })

            state = app.get_state(config)
            if state.next:
                # Paused for interrupt
                interrupt_data = state.tasks[0].interrupts[0].value
                print(f"\nAPPROVAL REQUIRED:")
                print(f"Agent wants to write to {interrupt_data.get('filepath')}")
                print("--- Content ---")
                print(interrupt_data.get('content'))
                print("---------------")
                
                user_input = input("Approve this change? [Y/n]: ").strip().lower()
                approved = user_input in ['y', 'yes', '']
                
                is_resume = True
                resume_data = approved
                if not approved:
                    print("Change rejected.")
                else:
                    print("Change approved.")
            else:
                print("\nJob Completed!")
                break
                
        except Exception as e:
            print(f"\nFatal Error: {e}")
            break

if __name__ == "__main__":
    from langgraph.types import Command
    main()
