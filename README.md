# Execution Agent

An autonomous, self-healing LangGraph ReAct agent that can explore, understand, and securely execute Python repositories.

## Overview

The Execution Agent takes a path to a local repository, explores its file structure, reads its documentation, and dynamically figures out how to run it. It utilizes `llm-sandbox` with a Docker backend to securely execute the code in an isolated environment without risking your host machine.

Most importantly, it features a **Self-Healing Loop**: If the repository code crashes during execution, the agent intercepts the stack trace, debugs the code, permanently fixes the bug on your host filesystem, and retries execution until it succeeds!

## Features

- 📂 **Multi-File Context**: Automatically copies the entire target repository into the execution sandbox, preserving local imports and dependencies.
- 🧠 **Autonomous Comprehension**: Reads `README.md`, `docs/`, and parses `argparse` implementations to figure out entry points and required parameters.
- 🛡️ **Secure Execution**: Runs the target codebase in an isolated Docker container via `llm-sandbox`.
- 🩺 **Self-Healing Execution**: Detects crashes and unhandled exceptions (even in `stdout`), uses LLM-powered reasoning to fix the underlying code bugs, and re-executes.

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

You can point the agent at any local Python repository.

```bash
python main.py "/absolute/path/to/repository"
```

### Providing Custom Instructions

If a repository lacks documentation or you want the agent to execute the code in a specific way (e.g., using a specific flag or dataset), you can pass a custom query:

```bash
python main.py "/absolute/path/to/repository" --query "Run the data processing script using the --verbose flag."
```

## Architecture

The project is modularized into the following components:
- `main.py`: The CLI entry point that initializes the graph.
- `agent/graph.py`: The LangGraph state graph wiring.
- `agent/nodes.py`: The LLM reasoning nodes, prompt definitions, and the `execute_node` which manages the Docker Sandbox and the self-healing conditional routing.
- `agent/tools.py`: The toolkit enabling the agent to read directories, read files, edit files, and submit commands.
- `agent/state.py`: The `TypedDict` defining the agent's state matrix.
