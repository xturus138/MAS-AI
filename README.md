# MAS AI — Multi-Agent Android Testing Framework

A multi-agent system (MAS) for automated Android GUI testing, built with LangGraph. Agents collaborate to observe, decide, execute, verify, and record test actions on a real Android device.

---

## Branch Guide

This repository uses a **multi-branch strategy** where `main` is the **main development timeline**.
The `feature/modular-workflow` branch is a **permanent experiment branch** — it will never be merged back.

### `main`
> Primary Branch — Future-proof MAS AI Framework.

The core branch of the MAS AI project. It will eventually host the fully integrated multi-agent system, combining autonomous goal-seeking with design-verified predefined scenarios (Figma integration).

- **Status**: Active Development.
- **Goal**: Full integration of all agents and adapters (Figma, ADB, etc.) into a production-ready QA framework.

```bash
git checkout main
```

---

### `feature/modular-workflow` ← *Experiment Branch (Permanent, Never Merged)*
> Multi-module refactor — clean separation of Predefined and Autonomous workflows.

Refactors the mixed codebase into two fully self-contained modules (`predefined/` and `autonomous/`), analogous to Kotlin multi-module clean architecture.

**Primary Purpose**: Collecting comparative research metrics for thesis justification. Use this branch to measure:
- **Task Success Rate**: Comparing goal achievement between modes.
- **Step Efficiency**: Measuring the number of actions to reach the goal.
- **Token Consumption**: Evaluating the cost-effectiveness of AI-driven planning.
- **Stagnation Frequency**: Tracking where the autonomous planner gets stuck.

- **`predefined/`** — Design-verified workflow using Figma prototypes and Excel scenarios.
- **`autonomous/`** — Goal-driven exploratory workflow using LLM planning.

### Mode 1: Predefined Workflow (Scenario-Based)

| Component | Detail |
| :--- | :--- |
| **Agents (6)** | Orchestrator, Observer, Decider, Executor, Reflector, Recorder |
| **Logic Source** | `scenario.xlsx` (Predefined steps) |
| **Figma Role** | **Critical**. Maps nodes, traces paths, and provides Gold Standard screenshots. |
| **Workflow** | **Discovery** (Figma) → **Execution** (Step-by-step) → **Verification** (Visual QA) → **Bridge** (Navigate to next) |

**Key Advantage**: Maximum reliability and pixel-perfect design verification.

---

### Mode 2: Autonomous Workflow (Goal-Based)

| Component | Detail |
| :--- | :--- |
| **Agents (6)** | Orchestrator (Planner), Observer, Decider, Executor, Reflector, Recorder |
| **Logic Source** | Scenario Description (High-level `task_goal`) |
| **Figma Role** | **None**. Planning is driven entirely by real-time UI analysis. |
| **Workflow** | **Goal Setting** → **Planning** (Next step) → **Execution** → **Progress Check** → **Re-plan** |

**Key Advantage**: Handles unexpected UI changes and explores undocumented paths.

---

**To switch workflow mode**, edit `.env`:
```env
WORKFLOW_STRATEGY=predefined   # uses predefined/ module
WORKFLOW_STRATEGY=autonomous   # uses autonomous/ module
```

### Configuration Distinction

| Variable | Predefined (Mode 1) | Autonomous (Mode 2) |
| :--- | :--- | :--- |
| `WORKFLOW_STRATEGY` | Set to `predefined` | Set to `autonomous` |
| `FIGMA_ACCESS_TOKEN` | **Required** (Path tracing/QA) | Not Used |
| `OPENAI_API_KEY` | Used (Discovery/Bridge) | **Critical** (Planning) |
| `TARGET_DEVICE` | Required (ADB) | Required (ADB) |

---

## Project Structure

```
MAS AI/
├── predefined/          ← Predefined workflow module
│   ├── orchestrator.py  ← Figma discovery, bridge, step-manager
│   ├── graph.py         ← LangGraph builder
│   └── runner.py        ← run_predefined()
│
├── autonomous/          ← Autonomous workflow module
│   ├── orchestrator.py  ← LLM-driven planner (no Figma)
│   ├── graph.py         ← LangGraph builder
│   └── runner.py        ← run_autonomous()
│
├── agents/              ← Shared agents (Observer, Decider, Executor, Reflector, Recorder)
├── adapters/            ← ADB + Figma adapters
├── core/                ← Shared models (AgentState) and utilities
├── shared/              ← Config (.env reader)
├── tools/               ← Observer and Executor tool sets
├── scenario.xlsx        ← Test scenarios input
└── main.py              ← Entry point
```

---

## Quick Start

1. Copy `.env.example` to `.env` and fill in your keys.
2. Set `WORKFLOW_STRATEGY` to `predefined` or `autonomous`.
3. Connect your Android device via ADB.
4. Run:
   ```bash
   python main.py
   ```
5. Results are saved to `outputs/<tcs_id>_<timestamp>/`.

---

## Experiment Metrics (Data Collection)

Use the table below to record your factual metrics for each scenario:

| Metric | Predefined (Mode 1) | Autonomous (Mode 2) |
| :--- | :--- | :--- |
| **Success Rate** | (Target: 100%) | (Target: Variable) |
| **Step Count** | (Optimal/Fixed) | (Dynamic/Exploratory) |
| **Token Cost** | (Predictable) | (Dynamic) |
| **Stagnation** | (Low - Retry Logic) | (High - Planning Loops) |
| **Visual Accuracy**| (Figma Verified) | (N/A) |
