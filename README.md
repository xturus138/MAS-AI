# MAS AI — Multi-Agent Android Testing Framework

A multi-agent system (MAS) for automated Android GUI testing, built with LangGraph. This framework supports fair comparative orchestration, enabling robust evaluation between predefined scripts and autonomous, LLM-driven task completion.

---

## Architecture & Modes

This framework operates on a **Shared Variable Experiment Model**, giving both workflows the exact same visual context and data baseline to perform operations.

### 1. Predefined Workflow (Scenario-Based)
- **Logic**: Strict index-based execution of sub-steps defined in `scenario.xlsx`.
- **Goal**: High reliability and precise regression verification against designers' intent.
- **Key Flow**: `Figma Discovery -> Step-by-Step Execution -> Visual QA -> Bridge Navigation`.

### 2. Autonomous Workflow (Goal-Based)
- **Logic**: Dynamic real-time planning based purely on the `task_goal` and live UI analysis.
- **Goal**: Robustness and unstructured exploratory testing.
- **Key Flow**: `Figma Discovery -> Dynamic Planning -> Execution -> Progress Check -> Re-plan`.

---

## Core Features

- **Figma Integration**: Automatically pulls prototype transitions to synthesize a "Gold Standard" screenshot used for truth verification.
- **Smart Re-Routing (Bridge)**: Dynamically computes navigation steps to bridge the app from its current state to the start state of the next scenario.
- **Self-Correction**: The **Reflector Agent** sanity-checks results after every step, triggering iterative recovery if a navigation fails.
- **Cost Observability**: Real-time dollar cost tracking for multi-provider LLM payloads (Google, Anthropic, OpenAI, DeepSeek, etc.).

---

## Data Collection & Metrics

Every test run generates highly granular diagnostic payloads in the output directory, including:

- **`final_metrics.json`**: Captures success status, efficiency metrics (steps, tokens elapsed), and design fidelity.
- **Execution Artifacts**: Snapshots, OCR readouts, `chat_logs.txt`, and individual tool output directories.

---

## Setup & Quick Start

### 1. Pre-requisites
1. Connect your physical Android device or emulator via ADB.
2. Ensure USB debugging is permitted.

### 2. Environment
Copy the configuration template and configure your models and keys:
```bash
cp .env.example .env
```

### 3. Toggle Execution Mode
Switch between strategies by updating `WORKFLOW_STRATEGY` in `.env`:
```env
WORKFLOW_STRATEGY=predefined   # Scenario-based execution
WORKFLOW_STRATEGY=autonomous   # Goal-driven exploration
```

### 4. Launch
Run the framework router:
```bash
python main.py
```
Find all results, screenshots, and metrics in the `outputs/` directory structure.
