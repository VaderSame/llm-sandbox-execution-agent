import os
import sys
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

from langchain_core.runnables import RunnableConfig

def agent_node(state: AgentState):
    llm = get_llm()
    tools = get_tools()
    llm_with_tools = llm.bind_tools(tools)
    
    sys_msg = SystemMessage(content=f"""You are a code execution agent. You have access to a repository at: {state.get('repo_path')}

Your primary task is to find the main entry point of this repository, figure out the required parameters, and submit it for execution.
CRITICAL INSTRUCTIONS:
1. Always prioritize reading documentation files (e.g., README.md, docs/, USAGE.md) first to understand how to run the repository and what parameters are required.
2. If documentation is lacking, read the code (like main.py) to deduce the required CLI arguments (e.g., from argparse).
3. Once you know exactly what command to run (e.g. python /sandbox/repo/main.py --param value), use the `submit_for_execution` tool to submit the command.
4. Note that the entire repository will be copied into `/sandbox/repo` inside the execution container, so format your commands assuming that path.
5. DO NOT try to execute the code yourself, rely on submit_for_execution.
""")
    
    messages = [sys_msg] + state["messages"]
    response = llm_with_tools.invoke(messages)
    
    execution_command = state.get("execution_command")
    if hasattr(response, "tool_calls") and response.tool_calls:
        for tool_call in response.tool_calls:
            if tool_call["name"] == "submit_for_execution":
                execution_command = tool_call["args"]["command"]
                
    return {"messages": [response], "execution_command": execution_command}

def debugger_node(state: AgentState):
    llm = get_llm()
    tools = get_tools()
    llm_with_tools = llm.bind_tools(tools)
    
    sys_msg = SystemMessage(content=f"""You are an expert Python debugger.
The execution agent failed to run the code. You have access to the repository at: {state.get('repo_path')}

CRITICAL INSTRUCTIONS:
1. Analyze the traceback or error provided in the messages.
2. Use the `read_file` tool to inspect the buggy code.
3. Use the `write_file` tool to apply a fix to the local repository.
4. When you believe the bug is fixed, use the `submit_for_execution` tool with the same execution command (or a modified one if the command itself was the issue) to test your fix.
5. You must call `submit_for_execution` to resume the graph.
""")
    
    messages = [sys_msg] + state["messages"]
    response = llm_with_tools.invoke(messages)
    
    execution_command = state.get("execution_command")
    if hasattr(response, "tool_calls") and response.tool_calls:
        for tool_call in response.tool_calls:
            if tool_call["name"] == "submit_for_execution":
                execution_command = tool_call["args"]["command"]
                
    return {"messages": [response], "execution_command": execution_command}

def execute_node(state: AgentState, config: RunnableConfig):
    command = state.get("execution_command")
    repo_path = state.get("repo_path")
    
    emit_event = config.get("configurable", {}).get("emit_event", lambda t, p: None)
    
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
            
            def stdout_callback(chunk: str):
                emit_event("sandbox_output", {"stream": "stdout", "chunk": chunk})
                sys.stdout.write(chunk)
                sys.stdout.flush()
                
            def stderr_callback(chunk: str):
                emit_event("sandbox_output", {"stream": "stderr", "chunk": chunk})
                sys.stderr.write(chunk)
                sys.stderr.flush()
                
            print("--- Sandbox Output ---")
            result = session.execute_command(
                wrapped_command, 
                on_stdout=stdout_callback, 
                on_stderr=stderr_callback
            )
            print("\n----------------------")
            
            emit_event("execution_result", {
                "success": result.exit_code == 0,
                "exit_code": result.exit_code,
                "stdout": result.stdout,
                "stderr": result.stderr
            })
            
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
        emit_event("execution_result", {
            "success": False,
            "exit_code": -1,
            "error": str(e)
        })
        return {"messages": [HumanMessage(content=f"Fatal Infrastructure Error: {e}\nAborting execution.")], "execution_success": None}
