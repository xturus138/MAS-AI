# AGENTS.md

This file provides guidance to Codex (Codex.ai/code) when working with code in this repository.

# MAS AI - Multi-Agent Android Testing Framework

## Project Summary

MAS AI is a multi-agent system for automated Android GUI testing built with LangGraph. It's designed for comparative research, enabling A/B testing between human-predefined logic and autonomous AI-driven logic on mobile applications.

## Core Purpose
- Automated Android Testing using computer vision, OCR, and LLM agents
- Comparative Research with two distinct orchestration strategies
- Modular Architecture separating concerns into adapters, agents, tools, workflows
- Metrics Collection generating structured JSON for research analysis

## Architecture Overview

Both workflows follow a LangGraph-based state machine:

1. **Orchestrator**: Decides next steps (predefined follows scenario.xlsx, autonomous uses LLM planning)
2. **Observer**: Analyzes screen state (OCR, computer vision, element detection)
3. **Decider**: Plans next action based on UI state and step instructions
4. **Executor**: Executes planned action on Android device via ADB
5. **Reflector**: Evaluates if action achieved its goal (with Figma comparison)
6. **Recorder**: Logs metrics and chat history for analysis

## Directory Structure

- `adapters/` - Platform-specific integrations (device, figma, llm)
- `agents/` - Core multi-agent logic (observer, decider, executor, reflector, recorder)
- `core/` - Models, ports, utils, workflow orchestration
  - `models/state.py` - AgentState TypedDict (shared state schema)
  - `ports/` - Abstract interfaces (ILLMClient, IDeviceClient)
  - `utils/` - Helpers (LLMFactory, xlsx_loader, token_counter)
  - `workflow/` - Orchestration logic (predefined, autonomous)
- `tools/` - Wrapped device tools (observer_tools, executor_tools)
- `shared/` - Global config and DTOs
- `main.py` - Entry point routing to predefined or autonomous
- `requirements.txt` - Python dependencies
- `.env` - Configuration (API keys, device, models)
- `scenario.xlsx` - Test cases

## Key Architectural Concepts

### AgentState (`core/models/state.py`)
Shared TypedDict flowing through LangGraph:
- Control: `tcs_id`, `current_step`, `sender`, `next_agent`
- UI Perception: `screenshot_path`, `ui_elements_summary`, `ocr_result`, `widgets`
- Decision: `action_plan`, `execution_result`, `is_completed`
- Metrics: `stagnation_count`, `recovery_attempts`, `action_history`, `chat_logs`
- Figma: `figma_enabled`, `figma_start_node_id`, `figma_end_node_id`, `figma_bridge_steps`

### Two Orchestration Modes

**Predefined Mode (Scenario-Based)**:
- Graph: `START → orchestrator → observer → decider → executor → reflector → recorder → orchestrator`
- Logic: Follows `sub_steps` from `scenario.xlsx` in strict order
- Orchestrator: Maps steps to Figma nodes, computes bridge navigation
- Figma: Critical for path tracing and visual verification

**Autonomous Mode (Goal-Based)**:
- Graph: All agents route BACK to orchestrator via `Command(goto=...)`
- Logic: Dynamically plans steps based on `task_goal` and current UI state
- Orchestrator: Real-time planning, stagnation detection, replanning
- Figma: Provides 'Gold Standard' screenshot for feedback (optional)

### Multi-Provider LLM Support
Supports: `openrouter`, `blackbox`, `openai`, `local`
Different models for different agent roles via environment variables and `LLMFactory`.

## Setup & Configuration

### Environment Variables (`.env`)

```env
WORKFLOW_STRATEGY=predefined  # or 'autonomous'
TARGET_DEVICE=<adb-device-id>
FIGMA_ACCESS_TOKEN=<your-figma-token>

OBSERVER_PROVIDER=blackbox
OBSERVER_API_KEY=<key>
OBSERVER_MODEL=<model-name>

DECIDER_PROVIDER=blackbox
DECIDER_API_KEY=<key>
DECIDER_MODEL=<model-name>

REFLECTOR_PROVIDER=blackbox
REFLECTOR_API_KEY=<key>
REFLECTOR_MODEL=<model-name>

ORCHESTRATOR_PROVIDER=blackbox
ORCHESTRATOR_API_KEY=<key>
ORCHESTRATOR_MODEL=<model-name>

MAX_TOKENS=25000
TOKEN_CONTEXT_WINDOW=128000
TOKEN_WARN_THRESHOLD=0.75
OUTPUT_DIR=outputs
```

### Test Cases (`scenario.xlsx`)
Columns: TCS ID, Menu, Sub1, Sub2, Scenario Desc, Test Steps, Expected Result, Test Type, User Role

## Development & Commands

### Local Setup

```bash
python -m venv venv
venv\Scripts\activate  # Windows
pip install -r requirements.txt
cp .env.example .env
# Edit .env with device ID, API keys
adb devices
```

### Running

**Predefined Mode**:
```bash
python main.py
# Outputs to: outputs/predefined/{tcs_id}_{timestamp}/
```

**Autonomous Mode**:
```bash
set WORKFLOW_STRATEGY=autonomous
python main.py
# Outputs to: outputs/autonomous/{tcs_id}_{timestamp}/
```

### Diagnostic Scripts

```bash
python check_figma_connection.py   # Test Figma API
python check_models.py             # Verify LLM provider connectivity
python clean_outputs.py            # Clear outputs directory
```

## Non-Obvious Conventions

### Token Management
- LLM Logger saves per-agent chat histories to isolated session files
- Token Counter tracks cumulative usage and warns at 75% of context window
- History auto-pruned by removing oldest messages when limits hit

### Stagnation Detection
- Tracks if UI state hasn't meaningfully changed across steps
- Reflected in `stagnation_count` (failure if > 3)
- Triggers replanning in autonomous mode

### Element Resolution
- Decider specifies actions by widget ID (integer), not coordinates
- Observer assigns IDs to detected UI elements
- Executor maps ID → bounds → coordinates (with ADB scaling calibration)

### Figma Integration Roles

**Predefined Mode**:
- Pre-scenario discovery maps navigation context → Figma node
- Traces expected path through Figma flow
- Uses Gold Standard screenshot for Reflector verification
- Bridges between scenarios by computing navigation steps

**Autonomous Mode**:
- Fetches Figma Gold Standard BEFORE starting (fair experiment)
- Reflector compares live screenshots against Figma reference
- NOT required for execution (fallback to OCR-only)

### LangGraph Patterns
- Autonomous: `Command(goto="agent_name")` for dynamic routing
- Predefined: Conditional edges for linear progression

### Screenshot Encoding
- Observer encodes images as WebP/JPEG base64 for LLM
- Max height: 720px (auto-scaled)
- Quality: 70% WebP, 75% JPEG for token efficiency

## Key Files

| File | Purpose |
|------|---------|
| `main.py` | Entry point routing to workflows |
| `shared/config.py` | Centralized configuration |
| `core/models/state.py` | Shared AgentState schema |
| `core/workflow/{mode}/runner.py` | Scenario loop initialization |
| `core/workflow/{mode}/graph.py` | LangGraph state machine |
| `core/workflow/{mode}/orchestrator.py` | Orchestration logic |
| `agents/*.py` | Agent implementations |
| `adapters/device/adb_adapter.py` | Android interface |
| `adapters/figma/figma_adapter.py` | Figma API client |
| `tools/*.py` | Tool wrappers |

## Research Metrics

Automatically generates `final_metrics.json` with:
- Task Success: `COMPLETED` / `STAGNATED` / `FAILED`
- Steps Taken: Total action count
- Tokens Used: LLM consumption
- Duration: Runtime in seconds
- Stagnation Count: Loop count
- Design Fidelity: Figma comparison result

## Debug Output Structure

Per step inside `outputs/{mode}/{tcs_id}_{timestamp}/step_X/`:
- `annotated.png` - Element detection overlay
- `action_plan.json` - Decider reasoning
- `reflector_report.json` - Reflector feedback
- `chat_logs.txt` - LLM conversation

## Extending the System

### Adding an Agent
1. Create `agents/your_agent.py`
2. Add method taking `AgentState`, returning state updates
3. Add node to `core/workflow/{mode}/graph.py` and wire edges

### Changing LLM Provider
Update `.env` `PROVIDER` and `API_KEY` — `LLMFactory` handles instantiation automatically, no code changes needed.

For research methodology details, see README.md.
