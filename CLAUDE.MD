# Project Instructions

You are helping build a backend-only AI application project for interview demonstration.

## Project Goal

Build a backend-only multi-agent open-source project evaluator.

Input:
- GitHub repository URL

Output:
- Structured open-source project evaluation report

## Current Scope

Only build the backend part.
Do not build frontend UI.
Do not add formal unit tests for now.
Use command-line checks to verify each step works.

## Tech Stack

- Python 3.13
- FastAPI
- LangGraph
- LangChain
- Pydantic
- Pydantic Settings
- Redis
- httpx
- python-dotenv
- uv

## Development Rules

1. Always inspect existing files before editing.
2. Before coding, produce a short implementation plan.
3. Use Pydantic models for structured data.
4. Keep API clients in app/tools/.
5. Keep agent logic in app/agents/.
6. Keep prompts in app/prompts/.
7. Prefer simple and stable code.
8. Do not put API keys in code.
9. Do not build frontend UI unless explicitly requested.
10. Do not add formal unit tests unless explicitly requested.

## Acceptance Criteria

- User can input a GitHub repository URL from the backend or command line.
- System can parse owner and repo.
- System can fetch GitHub repository data.
- System can fetch OpenDigger metrics when available.
- LangGraph workflow can run through main backend nodes.
- Final report includes score, strengths, risks, and suggestions.
- Backend API can expose an evaluation endpoint.
