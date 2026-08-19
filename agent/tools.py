import os
from typing import Annotated
from langchain_core.tools import tool
from langchain_core.runnables import RunnableConfig
from langgraph.types import interrupt
from langgraph.prebuilt import InjectedState

def get_safe_path(base_path: str, user_path: str) -> str:
    """Resolves a user-provided relative path safely within the base_path."""
    if not base_path:
        raise ValueError("Critical Error: base_path is missing")
        
    if user_path.startswith("/sandbox/repo"):
        user_path = user_path.replace("/sandbox/repo", "").lstrip("/")
    if not user_path:
        user_path = "."
        
    resolved_path = os.path.abspath(os.path.join(base_path, user_path))
    if not resolved_path.startswith(base_path):
        raise ValueError("Path escapes repository boundary")
    return resolved_path

@tool
def list_directory(directory_path: str, state: Annotated[dict, InjectedState]) -> str:
    """Lists files in the given relative directory path. Use '.' for the root of the repository."""
    repo_path = state.get("repo_path", "")
    try:
        safe_dir = get_safe_path(repo_path, directory_path)
        if not os.path.isdir(safe_dir):
            return f"Error: {directory_path} is not a directory."
        return "\n".join(os.listdir(safe_dir))
    except Exception as e:
        return f"Error: {e}"

@tool
def read_file(filepath: str, state: Annotated[dict, InjectedState]) -> str:
    """Reads the content of the given relative filepath. Use this to read documentation and code."""
    repo_path = state.get("repo_path", "")
    try:
        safe_file = get_safe_path(repo_path, filepath)
        if not os.path.isfile(safe_file):
            return f"Error: {filepath} is not a file."
        with open(safe_file, 'r', encoding='utf-8') as f:
            return f.read()
    except Exception as e:
        return f"Error: {e}"

@tool
def write_file(filepath: str, content: str, config: RunnableConfig, state: Annotated[dict, InjectedState]) -> str:
    """Overwrites the given relative filepath with the provided content. Use this to fix code bugs."""
    repo_path = state.get("repo_path", "")
    emit_event = config.get("configurable", {}).get("emit_event", lambda t, p: None)
    
    try:
        safe_file = get_safe_path(repo_path, filepath)
    except Exception as e:
        return f"Error resolving path: {e}"
    
    # Emit the event so the frontend logs it, but don't pause the graph yet
    emit_event("approval_required", {
        "type": "approval_required",
        "filepath": safe_file,
        "content": content
    })
    
    # Auto-approve
    response = True
    
    if not response:
        return f"Error: User denied the file modification for {filepath}."
            
    try:
        os.makedirs(os.path.dirname(safe_file), exist_ok=True)
        with open(safe_file, 'w', encoding='utf-8') as f:
            f.write(content)
        return f"Successfully wrote to {filepath}"
    except Exception as e:
        return f"Error writing to file: {e}"

@tool
def submit_for_execution(command: str) -> str:
    """
    Submits the chosen repository for execution with the specified command. 
    The entire repository will be copied and available in the sandbox at `/sandbox/repo`. 
    Provide the exact shell command to run the entrypoint, e.g., `python /sandbox/repo/main.py --arg1 val1`.
    This will trigger the sandbox execution and end your task.
    """
    return f"Execution submitted with command: {command}"

# Group the tools for the graph
get_tools = lambda: [list_directory, read_file, write_file, submit_for_execution]
