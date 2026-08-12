from typing import TypedDict, Annotated, Optional
from langchain_core.messages import BaseMessage
from langgraph.graph.message import add_messages

class AgentState(TypedDict):
    messages: Annotated[list[BaseMessage], add_messages]
    repo_path: str
    execution_command: Optional[str]
    execution_success: Optional[bool]
