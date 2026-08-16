import os
import json
import asyncio
import uuid
import tempfile
import zipfile
from fastapi import FastAPI, UploadFile, File, Form, BackgroundTasks, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from sse_starlette.sse import EventSourceResponse

from dotenv import load_dotenv
from langchain_core.messages import HumanMessage
from langgraph.types import Command

from fastapi.responses import PlainTextResponse

from agent import create_agent_graph

load_dotenv()

app = FastAPI(title="Execution Agent Service")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

agent_app = create_agent_graph()

# In-memory store for jobs
jobs = {}

async def run_agent_job(job_id: str, input_data: dict, is_resume: bool = False):
    def emit_event(event_type: str, payload: dict):
        jobs[job_id]["queue"].put_nowait({"type": event_type, "data": payload})
        
    config = {
        "configurable": {
            "thread_id": job_id, 
            "emit_event": emit_event
        }
    }
    
    try:
        if not is_resume:
            stream = agent_app.astream(input_data, config=config)
        else:
            stream = agent_app.astream(Command(resume=input_data.get("resume_data")), config=config)
            
        async for event in stream:
            # Emit node transition events
            for node_name, node_state in event.items():
                messages = node_state.get("messages", [])
                if messages:
                    last_msg = messages[-1]
                    
                    if node_name in ["agent", "debugger"]:
                        # Extract AI reasoning and tool calls
                        tool_calls = getattr(last_msg, "tool_calls", [])
                        emit_event("agent_turn", {
                            "node": node_name,
                            "content": last_msg.content,
                            "tool_calls": tool_calls
                        })
                    elif node_name in ["agent_tools", "debugger_tools"]:
                        # Extract Tool responses
                        emit_event("tool_result", {
                            "tool_name": last_msg.name,
                            "result": last_msg.content
                        })
                
        # Check if graph paused for interrupt
        state = agent_app.get_state(config)
        if state.next:
            interrupt_data = state.tasks[0].interrupts[0].value
            jobs[job_id]["status"] = "PAUSED_FOR_APPROVAL"
            emit_event("approval_required", interrupt_data)
        else:
            jobs[job_id]["status"] = "COMPLETED"
            emit_event("job_completed", {})
            
    except Exception as e:
        jobs[job_id]["status"] = "FAILED"
        emit_event("job_failed", {"error": str(e)})

@app.post("/execution-jobs")
async def create_job(
    background_tasks: BackgroundTasks,
    repo_name: str = Form(...),
    instruction: str = Form(...),
    chat_session_id: str = Form(...)
):
    job_id = str(uuid.uuid4())
    
    # Path to the shared code_repo directory
    base_repo_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "code_repo"))
    repo_path = os.path.join(base_repo_dir, repo_name)
    
    if not os.path.exists(repo_path):
        raise HTTPException(status_code=400, detail=f"Repository '{repo_name}' not found in code_repo.")
    
    jobs[job_id] = {
        "status": "RUNNING",
        "queue": asyncio.Queue(),
        "repo_path": repo_path,
        "chat_session_id": chat_session_id
    }
    
    initial_state = {
        "repo_path": repo_path,
        "messages": [HumanMessage(content=instruction)]
    }
    
    background_tasks.add_task(run_agent_job, job_id, initial_state)
    return {"job_id": job_id}

@app.get("/execution-jobs/{job_id}/stream")
async def stream_job(job_id: str):
    if job_id not in jobs:
        raise HTTPException(status_code=404, detail="Job not found")
        
    async def event_generator():
        q = jobs[job_id]["queue"]
        while True:
            event = await q.get()
            yield {"data": json.dumps(event)}
            if event["type"] in ["job_completed", "job_failed"]:
                break
                
    return EventSourceResponse(event_generator())

class ApprovalRequest(BaseModel):
    approved: bool

@app.post("/execution-jobs/{job_id}/approval")
async def approve_job(job_id: str, request: ApprovalRequest, background_tasks: BackgroundTasks):
    if job_id not in jobs:
        raise HTTPException(status_code=404, detail="Job not found")
        
    if jobs[job_id]["status"] != "PAUSED_FOR_APPROVAL":
        raise HTTPException(status_code=400, detail="Job is not paused for approval")
        
    jobs[job_id]["status"] = "RUNNING"
    jobs[job_id]["queue"].put_nowait({"type": "approval_received", "data": {"approved": request.approved}})
    
    background_tasks.add_task(run_agent_job, job_id, {"resume_data": request.approved}, is_resume=True)
    return {"status": "resumed"}

@app.get("/execution-jobs/{job_id}")
async def get_job(job_id: str):
    if job_id not in jobs:
        raise HTTPException(status_code=404, detail="Job not found")
    return {"job_id": job_id, "status": jobs[job_id]["status"]}

@app.get("/repos")
async def list_repos():
    base_repo_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "code_repo"))
    if not os.path.exists(base_repo_dir):
        return {"repos": []}
    
    repos = []
    for item in os.listdir(base_repo_dir):
        if os.path.isdir(os.path.join(base_repo_dir, item)):
            repos.append(item)
    return {"repos": repos}

@app.get("/repos/{repo_name}/tree")
async def get_repo_tree(repo_name: str):
    base_repo_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "code_repo"))
    repo_path = os.path.join(base_repo_dir, repo_name)
    
    if not os.path.exists(repo_path):
        raise HTTPException(status_code=404, detail=f"Repository '{repo_name}' not found.")
        
    def build_tree(current_path):
        tree = []
        try:
            for item in sorted(os.listdir(current_path)):
                # Skip __pycache__ and .git and node_modules
                if item in [".git", "__pycache__", "node_modules"]:
                    continue
                item_path = os.path.join(current_path, item)
                rel_path = os.path.relpath(item_path, repo_path).replace("\\", "/")
                is_dir = os.path.isdir(item_path)
                
                node = {
                    "name": item,
                    "path": rel_path,
                    "type": "directory" if is_dir else "file"
                }
                if is_dir:
                    node["children"] = build_tree(item_path)
                tree.append(node)
        except Exception:
            pass
        return tree
        
    return {"tree": build_tree(repo_path)}

@app.get("/repos/{repo_name}/file")
async def get_repo_file(repo_name: str, path: str):
    base_repo_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "code_repo"))
    repo_path = os.path.join(base_repo_dir, repo_name)
    
    if not os.path.exists(repo_path):
        raise HTTPException(status_code=404, detail=f"Repository '{repo_name}' not found.")
        
    # Ensure secure path resolution
    target_path = os.path.abspath(os.path.join(repo_path, path))
    if not target_path.startswith(repo_path):
        raise HTTPException(status_code=403, detail="Access denied")
        
    if not os.path.isfile(target_path):
        raise HTTPException(status_code=404, detail="File not found")
        
    try:
        with open(target_path, "r", encoding="utf-8") as f:
            content = f.read()
        return {"content": content}
    except Exception as e:
        # Fallback to reading as binary and decoding ignoring errors or just stringify
        try:
            with open(target_path, "rb") as f:
                content = f.read().decode("utf-8", errors="replace")
            return {"content": content}
        except Exception as inner_e:
            raise HTTPException(status_code=500, detail=str(inner_e))

# ==========================================
# Repository Browsing Endpoints
# ==========================================

def get_base_repo_dir() -> str:
    return os.path.abspath(os.path.join(os.path.dirname(__file__), "code_repo"))

def get_safe_repo_path(repo_name: str) -> str:
    base_dir = get_base_repo_dir()
    repo_path = os.path.abspath(os.path.join(base_dir, repo_name))
    if not repo_path.startswith(base_dir) or not os.path.isdir(repo_path):
        raise HTTPException(status_code=404, detail="Repository not found")
    return repo_path

@app.get("/repos")
async def list_repos():
    base_dir = get_base_repo_dir()
    if not os.path.exists(base_dir):
        return []
    
    repos = [d for d in os.listdir(base_dir) if os.path.isdir(os.path.join(base_dir, d))]
    return repos

@app.get("/repos/{repo_name}/tree")
async def get_repo_tree(repo_name: str):
    repo_path = get_safe_repo_path(repo_name)
    
    def build_tree(current_path: str, relative_to: str):
        name = os.path.basename(current_path)
        rel_path = os.path.relpath(current_path, relative_to)
        if rel_path == ".":
            rel_path = ""
            
        node = {
            "name": name,
            "path": rel_path.replace("\\", "/"),
            "type": "directory" if os.path.isdir(current_path) else "file"
        }
        
        if os.path.isdir(current_path):
            node["children"] = []
            try:
                for child in sorted(os.listdir(current_path)):
                    # Ignore .git or pycache if needed, but we'll include all by default
                    child_path = os.path.join(current_path, child)
                    node["children"].append(build_tree(child_path, relative_to))
            except PermissionError:
                pass
                
        return node
        
    return build_tree(repo_path, repo_path)



@app.get("/repos/{repo_name}/file", response_class=PlainTextResponse)
async def get_repo_file(repo_name: str, path: str):
    repo_path = get_safe_repo_path(repo_name)
    
    # Resolve absolute path and ensure it stays within the repo
    file_path = os.path.abspath(os.path.join(repo_path, path))
    if not file_path.startswith(repo_path):
        raise HTTPException(status_code=403, detail="Access denied")
        
    if not os.path.isfile(file_path):
        raise HTTPException(status_code=404, detail="File not found")
        
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            return f.read()
    except UnicodeDecodeError:
        raise HTTPException(status_code=400, detail="Cannot read binary file")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
