import os
import json
import asyncio
import uuid
import tempfile
import zipfile
from fastapi import FastAPI, UploadFile, File, Form, BackgroundTasks, HTTPException
from pydantic import BaseModel
from sse_starlette.sse import EventSourceResponse

from dotenv import load_dotenv
from langchain_core.messages import HumanMessage
from langgraph.types import Command

from agent import create_agent_graph

load_dotenv()

app = FastAPI(title="Execution Agent Service")
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
