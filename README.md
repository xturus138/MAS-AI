# MAS AI — Multi-Agent Android Testing Framework

A multi-agent system (MAS) for automated Android GUI testing, built with LangGraph. Agents collaborate to observe, decide, execute, verify, and record test actions on a real Android device.

---

## Branch Guide

This repository uses a **multi-branch strategy** where `multiagent-workflow` is the **main development timeline**.
The `feature/modular-workflow` branch is a **permanent experiment branch** — it will never be merged back.

### `main`
> Stable baseline — AI-Driven workflow with `SupervisorAgent`.

The original autonomous architecture. A single high-level `task_goal` is given and the `SupervisorAgent` decides what to do next at each step.

- **Workflow**: `task_goal` → Observer → Decider → Executor → Supervisor (re-plan) → loop
- **Orchestration**: `SupervisorAgent` dynamically generates subgoals
- **No** Figma integration
- **No** scenario file (Excel)

```bash
git checkout main
```

---

### `multiagent-workflow`
> Predefined + Figma workflow — the last clean baseline for metrics collection.

Introduces scenario-based execution from `scenario.xlsx` and full **Figma prototype integration** for visual QA validation. This branch is **preserved as-is** for experiment data collection.

- **Workflow**: Load scenario → Figma discovery → Observer → Decider → Executor → Reflector → Recorder → Orchestrator → loop
- **Orchestration**: `OrchestratorAgent` manages step index and retries
- **Figma**: Maps navigation context to Figma frames, traces prototype paths, fetches Gold Standard screenshots
- **Bridge**: Computes navigation steps between scenarios using Figma + LLM

```bash
git checkout multiagent-workflow
```

> ⚠️ This is the **main development timeline**. All production-level changes and future features should be added here.

---

### `feature/modular-workflow` ← *Experiment Branch (Permanent, Never Merged)*
> Multi-module refactor — clean separation of Predefined and Autonomous workflows.

Refactors the mixed codebase into two fully self-contained modules (`predefined/` and `autonomous/`), analogous to Kotlin multi-module clean architecture. This branch exists **solely for experiment comparison** — it is branched off `multiagent-workflow` and will never be merged into any timeline branch.

- **`predefined/`** — owns Figma discovery, bridge navigation, step-index orchestration
- **`autonomous/`** — owns LLM-driven planning, no Figma dependency
- **`main.py`** — 8-line thin entry point, delegates to the correct module

```bash
git checkout feature/modular-workflow
```

**To switch workflow mode**, edit `.env`:
```env
WORKFLOW_STRATEGY=predefined   # uses predefined/ module
WORKFLOW_STRATEGY=autonomous   # uses autonomous/ module
```

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
