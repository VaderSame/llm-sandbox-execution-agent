# Execution Agent

An autonomous, self-healing LangGraph ReAct agent that can explore, understand, and securely execute Python repositories.

## Overview

The Execution Agent takes a `.zip` archive of a target repository via an HTTP API, extracts it to an isolated scratch workspace, explores its file structure, reads its documentation, and dynamically figures out how to run it. It utilizes `llm-sandbox` with a Docker backend to securely execute the code in an isolated environment without risking your host machine.

Most importantly, it features a **Self-Healing Loop**: If the repository code crashes during execution, the agent intercepts the stack trace, debugs the code, permanently fixes the bug on the local filesystem, and retries execution until it succeeds!

This project is built as a **headless FastAPI service** that streams Server-Sent Events (SSE). It is designed to be programmatically called by other AI coding agents to serve as an independent, sandboxed execution environment.

## Features

- 📂 **Zip Handoff**: Accepts codebase `.zip` uploads over HTTP and isolates each execution job in a clean temporary directory.
- 🧠 **Autonomous Comprehension**: Reads `README.md`, `docs/`, and parses `argparse` implementations to figure out entry points and required parameters.
- 🛡️ **Secure Execution**: Runs the target codebase in an isolated Docker container via `llm-sandbox`.
- 🩺 **Self-Healing Execution**: Detects crashes and unhandled exceptions, uses LLM-powered reasoning to fix the underlying code bugs, and re-executes.
- 📡 **SSE Streaming API**: Exposes a real-time event stream (`agent_turn`, `tool_result`, `sandbox_output`) for rich frontend UIs.
- ⏸️ **Human-in-the-Loop Interrupts**: Uses LangGraph's native `interrupt()` feature to pause execution during dangerous operations (like file writes) and awaits HTTP approval.

## Prerequisites

1. Python 3.10+
2. Docker Engine (Docker Desktop must be running)
3. An OpenAI-compatible API Key (Default setup uses OpenRouter and `openai/gpt-4o`)

## Installation

1. Clone this repository.
2. Install the required dependencies:
   ```bash
   pip install -r requirements.txt
   ```
3. Create a `.env` file from the example:
   ```bash
   cp .env.example .env
   ```
4. Add your API credentials to `.env`.

## Usage

### 1. Start the Server
Start the Uvicorn ASGI server to expose the FastAPI endpoints:

```bash
uvicorn server:app --host 0.0.0.0 --port 8000
```

### 2. API Endpoints

- `POST /execution-jobs`: Accepts `multipart/form-data` with `repo_zip` (the codebase) and `instruction`. Creates a job and starts the agent in the background. Returns `{ "job_id": "..." }`.
- `GET /execution-jobs/{job_id}/stream`: Connects to a Server-Sent Events (SSE) stream to receive live updates from the agent's brain and the execution sandbox.
- `POST /execution-jobs/{job_id}/approval`: Accepts `{ "approved": true }` to resume the graph when it is paused waiting for permission to modify a file.
- `GET /execution-jobs/{job_id}`: Polls the current status of the job.

*(Visit `http://localhost:8000/docs` to interact with the auto-generated Swagger UI!)*

### 3. Testing Locally
A client script is provided to test the end-to-end API flow from your terminal. Ensure the server is running, and in a separate terminal run:

```bash
python test_api.py
```
This script will mock a Code Agent by zipping a test folder, hitting the `/execution-jobs` endpoint, auto-approving file writes, and printing the SSE stream perfectly formatted to the console.

## Architecture

The project is modularized into the following components:
- `server.py`: The FastAPI application, API routers, and SSE stream handlers.
- `agent/graph.py`: The LangGraph state graph wiring, compiled with a `MemorySaver` checkpointer to support interrupts.
- `agent/nodes.py`: The LLM reasoning nodes, prompt definitions, and the `execute_node` which manages the Docker Sandbox and the self-healing conditional routing.
- `agent/tools.py`: The toolkit enabling the agent to read directories, read files, edit files, and submit commands.
- `agent/state.py`: The `TypedDict` defining the agent's state matrix.
