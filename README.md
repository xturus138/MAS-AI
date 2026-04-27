# MAS AI — Multi-Agent Android Testing Framework (Modular Research Edition)

A multi-agent system (MAS) for automated Android GUI testing, built with LangGraph. This branch is specifically refactored for **Comparative Research**, enabling a fair A/B test between human-predefined logic and autonomous AI-driven logic.

---

## Branch Guide

| Branch | Role | Description |
| :--- | :--- | :--- |
| `main` | **Primary** | The future-proof integrated timeline for the entire MAS AI framework. |
| `feature/modular-workflow` | **Experiment** | **Current Branch.** Self-contained modules for research metrics. *Never merged.* |

---

## Fair Experiment Architecture

This repository is designed for a **Controlled Variable Experiment**. To ensure scientific rigor, both workflows are given the **exact same information context**:

1.  **Shared Knowledge**: Both modes read the same `scenario.xlsx` and perform the same **Figma Design Discovery** before starting.
2.  **Shared Validation**: Both modes use the **Figma Gold Standard** screenshot to verify the final result in the Reflector.
3.  **The Single Variable**: The only difference is the **Orchestration Brain**:
    *   **Predefined Mode**: Static orchestration following a human-written script.
    *   **Autonomous Mode**: Dynamic orchestration where the AI plans its own path.

### Mode 1: Predefined Workflow (Scenario-Based)
- **Logic**: Strict index-based execution of sub-steps.
- **Goal**: High reliability and design fidelity verification.
- **Workflow**: `Figma Discovery -> Step-by-Step Execution -> Visual QA -> Bridge Navigation`.

### Mode 2: Autonomous Workflow (Goal-Based)
- **Logic**: Real-time planning based on the `task_goal` and live UI state.
- **Goal**: Robustness and exploratory testing.
- **Workflow**: `Figma Discovery -> Dynamic Planning -> Execution -> Progress Check -> Re-plan`.

---

## Data Collection & Metrics

Every test run automatically generates a **`final_metrics.json`** file in the output directory. This file is designed for automated data collection and includes:

- **Task Success Rate**: Binary result (SUCCESS/FAILED).
- **Step Efficiency**: Total number of actions taken.
- **Stagnation Frequency**: Count of loops or "stuck" states.
- **Design Fidelity**: Reflector's judgment against the Figma Gold Standard.

---

## Comparative Analysis: Case Study `NOTE-001`

Below are the results of the experiment from both orchestration setups using **identical agent logic** and tools.

| Metric | AI-Driven Workflow (Autonomous) | Predefined Workflow (Scenario-Based) |
| :--- | :--- | :--- |
| **Status (Final Goal)** | 🔴 STAGNATED (Looping 7 cycles) | 🟢 **SUCCESS** |
| **Efficiency (Tokens)** | 9,679 | **6,087** |
| **Duration (Seconds)** | 265.82 | **218.92** |
| **Physical Actions** | 3 | **5** |
| **Stagnation Count** | 3 | **0** |

### How to Replicate
To replicate these results for your own research:
1.  **Autonomous Run**: Set `WORKFLOW_STRATEGY=autonomous` in `.env` and run `python main.py`.
2.  **Predefined Run**: Set `WORKFLOW_STRATEGY=predefined` in `.env` and run `python main.py`.
3.  **Ensure Consistency**: Use the same `scenario.xlsx` and target device for both runs.

### How to Find Results
All experiment data is saved in the `outputs/` directory:
- **Autonomous Results**: `outputs/autonomous/<tcs_id>_<timestamp>/final_metrics.json`
- **Predefined Results**: `outputs/predefined/<tcs_id>_<timestamp>/final_metrics.json`
- **Visual Evidence**: Each run directory contains `step_x/` folders with screenshots and `chat_logs.txt`.

---

## Setup & Configuration

### 1. Environment Toggle (`.env`)
Switch between modes by editing the `WORKFLOW_STRATEGY` variable:
```env
WORKFLOW_STRATEGY=predefined   # Runs Mode 1
WORKFLOW_STRATEGY=autonomous   # Runs Mode 2
```

### 2. Configuration Distinction
| Variable | Predefined (Mode 1) | Autonomous (Mode 2) |
| :--- | :--- | :--- |
| `FIGMA_ACCESS_TOKEN` | **Required** (Path tracing) | **Required** (Goal Discovery) |
| `ORCHESTRATOR_MODEL` | Used for Mapping/Bridging | **Critical** for Planning |

---

## Quick Start
1. Connect your Android device via ADB.
2. Ensure `scenario.xlsx` contains your test cases.
3. Run the entry point:
   ```bash
   python main.py
   ```
4. Find research data in: `outputs/<tcs_id>_<timestamp>/final_metrics.json`
