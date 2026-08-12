import os
from langchain_core.tools import tool

from langgraph.types import interrupt

@tool
def list_directory(directory_path: str) -> str:
    """Lists files in the given absolute directory path."""
    try:
        if not os.path.isdir(directory_path):
            return f"Error: {directory_path} is not a directory."
        return "\n".join(os.listdir(directory_path))
    except Exception as e:
        return f"Error: {e}"

@tool
def read_file(filepath: str) -> str:
    """Reads the content of the given absolute filepath. Use this to read READMEs, docs, and code files."""
    try:
        if not os.path.isfile(filepath):
            return f"Error: {filepath} is not a file."
        with open(filepath, 'r', encoding='utf-8') as f:
            return f.read()
    except Exception as e:
        return f"Error: {e}"

@tool
def write_file(filepath: str, content: str) -> str:
    """Overwrites the given absolute filepath with the provided content. Use this to fix code bugs."""
    # Request approval from the frontend client instead of blocking terminal
    # interrupt() raises a special exception to suspend the graph, so DO NOT wrap it in a blanket try/except
    response = interrupt({
        "type": "approval_required",
        "filepath": filepath,
        "content": content
    })
    
    # response should be boolean depending on what we pass back to resume
    if not response:
        return f"Error: User denied the file modification for {filepath}."
            
    try:
        with open(filepath, 'w', encoding='utf-8') as f:
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
