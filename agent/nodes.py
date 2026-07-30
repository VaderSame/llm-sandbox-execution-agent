import os
from langchain_openai import ChatOpenAI
from langchain_core.messages import SystemMessage, HumanMessage
from langgraph.graph import END

from llm_sandbox import SandboxSession
from .state import AgentState
from .tools import get_tools

def get_llm():
    return ChatOpenAI(
        openai_api_key=os.environ.get("OPENAI_API_KEY"),
        openai_api_base=os.environ.get("OPENROUTER_SERVER"),
        model_name=os.environ.get("MODEL_ID"),
        temperature=0
    )

def agent_node(state: AgentState):
    llm = get_llm()
    tools = get_tools()
    llm_with_tools = llm.bind_tools(tools)
    
    sys_msg = SystemMessage(content=f"""You are a code execution agent. You have access to a repository at: {state['repo_path']}

Your primary task is to find the main entry point of this repository, figure out the required parameters, and submit it for execution.
CRITICAL INSTRUCTIONS:
1. Always prioritize reading documentation files (e.g., README.md, docs/, USAGE.md) first to understand how to run the repository and what parameters are required.
2. If documentation is lacking, read the code (like main.py) to deduce the required CLI arguments (e.g., from argparse).
3. Once you know exactly what command to run (e.g. python /sandbox/repo/main.py --param value), use the `submit_for_execution` tool to submit the command.
4. Note that the entire repository will be copied into `/sandbox/repo` inside the execution container, so format your commands assuming that path.
5. DO NOT try to execute the code yourself, rely on submit_for_execution.
6. SELF-HEALING: If an execution fails, you will receive the error log. You must read the crashing file using `read_file`, fix the code using `write_file`, and then call `submit_for_execution` again!
""")
    
    messages = [sys_msg] + state["messages"]
    response = llm_with_tools.invoke(messages)
    
    execution_command = state.get("execution_command")
    if hasattr(response, "tool_calls") and response.tool_calls:
        for tool_call in response.tool_calls:
            if tool_call["name"] == "submit_for_execution":
                execution_command = tool_call["args"]["command"]
                
    return {"messages": [response], "execution_command": execution_command}

def should_continue(state: AgentState):
    messages = state["messages"]
    last_message = messages[-1]
    
    if hasattr(last_message, "tool_calls") and last_message.tool_calls:
        if any(tc["name"] == "submit_for_execution" for tc in last_message.tool_calls):
            return "execute_node"
        return "tools"
    return END

def execute_node(state: AgentState):
    command = state.get("execution_command")
    repo_path = state.get("repo_path")
    
    if not command:
        return {"messages": [HumanMessage(content="No execution command was set.")], "execution_success": False}
        
    print(f"\n--- Preparing Sandbox Execution ---")
    print(f"Mounting: {repo_path} -> /sandbox/repo")
    print(f"Command: {command}\n")
    
    try:
        with SandboxSession(lang="python") as session:
            # Copy the entire repository into the sandbox
            session.copy_to_runtime(repo_path, "/sandbox/repo")
            
            wrapped_command = f'sh -c "cd /sandbox/repo && {command}"'
            result = session.execute_command(wrapped_command)
            
            print("--- Sandbox Output ---")
            print(result.stdout)
            
            if result.exit_code == 0 and not result.stderr:
                # Even if exit code is 0, check if the script intercepted an error and printed it
                stdout_lower = result.stdout.lower() if result.stdout else ""
                if "error" in stdout_lower or "exception" in stdout_lower or "traceback" in stdout_lower:
                    print("--- Sandbox Caught Error in Stdout ---")
                    error_msg = f"Execution exited with code 0, but the output contains an error.\nStdout:\n{result.stdout}\n\nPlease analyze this error, fix the local repository code using the `write_file` tool if necessary, and call `submit_for_execution` again."
                    return {"messages": [HumanMessage(content=error_msg)], "execution_success": False}
                
                return {"messages": [HumanMessage(content=f"Execution completed successfully!\nStdout:\n{result.stdout}")], "execution_success": True}
            else:
                print("--- Sandbox Error ---")
                print(result.stderr)
                error_msg = f"Execution failed with exit code {result.exit_code}.\nStdout:\n{result.stdout}\nStderr:\n{result.stderr}\n\nPlease analyze this error, fix the local repository code using the `write_file` tool if necessary, and call `submit_for_execution` again."
                return {"messages": [HumanMessage(content=error_msg)], "execution_success": False}
                
    except Exception as e:
        print(f"Failed to execute: {e}")
        return {"messages": [HumanMessage(content=f"Execution failed: {e}\nPlease fix this issue and try again.")], "execution_success": False}
