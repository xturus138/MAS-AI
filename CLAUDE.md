# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

MAS AI is a multi-agent system for automated Android GUI testing, built with LangGraph. It has two modes: **predefined** (scenario-based, driven by `scenario.xlsx`) and **autonomous** (goal-driven, LLM-planned). Tests execute on physical Android devices via ADB.

## Bayesian test-selection context — still an open research question

The repository contains a representation-comparison pilot at
`experiment/bayesian/three_method_representation_comparison.ipynb`. It is not
the implemented multi-agent workflow and it is not evidence that Bayesian
Optimization (BO) is the thesis method. The pilot uses dummy outcomes only;
do not call them real Firebase Chat defects.

The open hypothesis is to run all 69 QA cases once, record actual execution
outcomes, and use that table only as a hidden oracle for offline sequential
replay. A BO surrogate would receive an outcome only after selecting that
case. The start policy remains undecided: coverage-first warm start with one
test per mandatory feature, or a cold start whose first choice is constrained
by coverage. This is not a conventional train/test split. AI token or credit
cost is not currently measurable, so no claim about credit savings is valid.

Before changing production agents, prompts, or workflow logic for this idea,
read `Hasil AI/JAIST/EXPERIMENT_HYPOTHESIS_BO_QA_TEST_REDUCTION.md` in the
research-document workspace. Treat its conclusions as hypotheses, not settled
requirements.

## Current engineering priority — 69-case predefined baseline

The immediate implementation task is **not** Bayesian Optimization. Make the
predefined workflow ready to execute all 69 Firebase Chat QA cases from
`scenarios/firebase_chat/scenario.xlsx` as one reliable, stateful batch. This
run is intended to create execution history; it does not yet select or remove
test cases.

The app should normally continue from the state left by the preceding case.
Before each next case, check whether the current state can satisfy that case's
starting navigation context. If not, perform and log a recovery transition.
Recovery actions are operational setup, not QA test steps: never prepend or
otherwise mutate the workbook's original `Test Step` value.

Batch requirements:

- run all cases in workbook order, but continue after an individual technical
  error or scenario failure;
- record a distinct outcome for success, functional anomaly/failure, stalled
  scenario, and technical error;
- support safe resume/re-run of unfinished cases without overwriting earlier
  evidence;
- preflight the device, app, required permissions/accounts, and selected
  configuration before the first case;
- produce one final aggregate summary plus per-case evidence and logs.

The original Excel schema must be preserved. Do not add columns. Populate only
the existing execution fields: `Time Testing`, `Testing Status`, the first
`Updated At`, `Testing By`, `OK Evid.`, and `Issue Status`. Do not write to
the downstream developer-tracking columns. Store detailed actual observations
in the per-case artifacts referenced by `OK Evid.`.

Observer DSE is a separate experiment and must remain disabled for this batch
(`OBSERVER_UNCERTAINTY_ENABLED=false`). Keep its source code intact; do not
delete or integrate it into batch outcomes, selection, or stopping decisions.

## Commands

```bash
# Run the framework (reads WORKFLOW_STRATEGY from .env)
python main.py

# Diagnostics
python tests/check_figma_connection.py
python tests/check_models.py

# Automated test suite
python -m pytest -q

# Legacy cleanup (dry-run first, then apply)
python scripts/cleanup_outputs.py --dry-run
python scripts/cleanup_outputs.py --apply
```

The repository has a pytest suite. Some files under `tests/` are standalone
device/API diagnostics, but `python -m pytest -q` is the standard local
regression command and does not require a connected Android device.

## Architecture

### Agent Loop (LangGraph State Machine)

Both modes share the same 5-agent cycle flowing through `AgentState` (TypedDict in `core/models/state.py`):

```
ORCHESTRATOR → OBSERVER → DECIDER → EXECUTOR → REFLECTOR → (back to ORCHESTRATOR)
```

- **Predefined**: linear pipeline with conditional edge at orchestrator (`_next_step_or_end`)
- **Autonomous**: hub-and-spoke — every agent returns to orchestrator, which decides next agent via `Command(goto=...)`

> Note: the thesis architecture diagram for predefined mode simplifies some of this loop (Recorder timing, the memory box, bridge navigation, retry logic). See `docs/predefined-workflow-diagram-gaps.md` for the full diagram-vs-code comparison and open action items.

### Agents (`agents/`)

Agents are distributed across `agents/` and `core/workflow/`:

- `observer_agent.py` → `analyze()` — captures screenshot via ADB, then detects widgets via `OBSERVER_DETECTION_METHOD`:
  - `"omniparser"`: Local YOLOv8 (icon detection) + EasyOCR (text) + Florence-2 (batch icon captioning). In-memory model caching. Generates structured `SEMANTIC_MAP` directly without an extra cloud LLM call (0 LLM token cost).
  - `"llm"`: Zero-shot VLM grounding (`_detect_widgets_via_llm()`, one structured-output call per screen) + cloud LLM semantic interpretation.
  - `"cv_ocr"`: Classical Canny+region-fill + EasyOCR + `_merge_and_filter` (fallback for API/CUDA failure).
  - Regardless of method, dumps uiautomator XML to refine widget coordinates via IoU matching. Unmatched actionable XML elements are appended. Produces `observer_analysis` and `widgets`.
- `decider_agent.py` → `decide()` — takes observer output + sub-step instruction, produces `ActionPlan` (structured Pydantic model)
- `executor_agent.py` → `execute()` — resolves widget ID → coordinates, sends ADB command via `ExecutorTools`
- `reflector_agent.py` → `evaluate()` — verifies action result, produces PASSED/FAILED verdict; on final step does 3-way verification (screenshot vs. expected text vs. Figma Gold Standard)
- **Orchestrator** — lives in `core/workflow/{mode}/orchestrator.py` (not `agents/`). Predefined orchestrator runs linear step pipeline; autonomous orchestrator decides next agent via LLM `Command(goto=...)`.
  - Predefined orchestrator's `orchestrate()` also owns retry/failure logic: PASS advances the step index and resets retry count; FAIL increments retry count (capped at 3, then the whole scenario aborts); a `[SYSTEM_ERROR]` in the reflector's reasoning is treated as a technical failure and advances without penalizing the app. See `core/workflow/predefined/orchestrator.py:409`.
  - Predefined orchestrator also computes **bridge navigation** (`compute_bridge()`) — extra steps injected between two scenarios so the app moves from wherever scenario N ended to the start screen scenario N+1 expects. Called from `runner.py` after each scenario completes, only when a Figma adapter is configured. See `core/workflow/predefined/orchestrator.py:344`.
- `recorder_agent.py` — not a graph node; called once post-run via `finalize_run_metrics()`

### MIRIX Memory System (`memory/`)

All persistent context lives outside LangGraph state. `MIRIXMemorySystem` (`memory/meta_manager.py`) is the single gateway — no agent reads/writes stores directly.

**Two operations:**
- `memory.retrieve(topic)` — parallel search across Episodic + Semantic stores, returns tagged context string
- `memory.update(packet)` — routes dict fields to the correct store in parallel

**Six stores:**

| Store | Backend | Purpose |
|-------|---------|---------|
| Core | JSON | Immutable session facts (task_goal, expected_result, test_type) |
| Episodic | SQLite + FTS5 | Timestamped event log (actor, step, event_type) |
| Semantic | SQLite + FTS5 | UI concepts/widget descriptions (cross-step recall) |
| Procedural | JSON | Ordered sub-steps from scenario.xlsx |
| Resource | JSON + disk | Binary assets (Figma gold standard, screenshots) |
| Knowledge Vault | JSON | Domain heuristics accumulated across runs |

Schemas in `memory/schemas.py`. Retrieval logic in `memory/retrieval/active_retrieval.py`.

### Ports & Adapters (`core/ports/`, `adapters/`)

- `ILLMClient` — abstract LLM interface; `LangChainAdapter` implements it
- `IDeviceClient` — abstract device interface; `ADBAdapter` implements it
- `FigmaAdapter` — Figma API integration for prototype discovery and gold-standard screenshots

### Prompts (`shared/prompts/`)

Per-agent prompt modules with few-shot examples and chain-of-thought strategies:
`observer_prompts.py`, `decider_prompts.py`, `reflector_prompts.py`, `orchestrator_prompts.py`, `predefined_orchestrator_prompts.py`.

### Provider Switching (`PROVIDER_SWITCH.md`)

Quick-switch cheat sheet for swapping all 4 agents between Gemini / Blackbox / OpenAI / Azure providers. Copy-paste the block into `.env`.

### Configuration (`shared/config.py`)

All config is env-driven via `.env` with fallbacks in code. Key variables:

All config is env-driven via `.env` with fallbacks in code. Key variables:
- `WORKFLOW_STRATEGY` — `"predefined"` or `"autonomous"`
- Per-agent `*_PROVIDER`, `*_MODEL`, `*_API_KEY`, `*_BASE_URL` for observer/decider/reflector/orchestrator
- `TARGET_DEVICE` — ADB device ID
- `FIGMA_ACCESS_TOKEN`, `FIGMA_URL_QA` — Figma integration
- `OBSERVER_DETECTION_METHOD` — `"omniparser"` (local YOLOv8 + OCR + Florence-2 captioning, 0 LLM call in observer), `"llm"` (zero-shot VLM grounding), or `"cv_ocr"` (classical Canny+OCR fallback); also used by `core/calibration/run_calibration.py`

### Process Logging (`core/utils/process_logger.py`)

Every scenario writes `process.log` to its output directory. All agents call `logger.log(COMPONENT, message, detail)`. Thread-safe.

### Output Structure

All run output paths are created by `core/utils/output_manager.py`.

```
outputs/
├── runs/
│   ├── predefined/
│   │   └── YYYY-MM-DD/
│   │       └── {tcs_id}__{timestamp}/
│   └── autonomous/
│       └── YYYY-MM-DD/
│           └── {tcs_id}__{timestamp}/
├── shared/
│   └── predefined_memory/
└── indexes/
    ├── latest.json
    ├── predefined_runs.json
    └── autonomous_runs.json
```

Each run folder:

```
{tcs_id}__{timestamp}/
├── process.log
├── final_metrics.json
├── run_summary.json
├── run_overview.md
├── logs/
│   ├── chat_logs.txt
│   └── llm/
│       └── {agent}_{timestamp}.json
├── reports/
│   ├── test_report.xlsx
│   └── interaction_script.json
├── figma/
│   ├── gold_standard.png
│   └── end_state.png
├── memory/
│   ├── core.json, procedural.json, resource.json, vault.json
│   └── episodic.db, semantic.db
└── steps/
    ├── 001/
    ├── 002/
    └── 002_retry_01/
```

Legacy cleanup: `python scripts/cleanup_outputs.py --dry-run`, then
`python scripts/cleanup_outputs.py --apply`. Flat JSON files in
`outputs/llm_logs/` are moved without deletion into the ignored local archive
`outputs/archive/llm_logs/{date}/`.

### Key Conventions

- `AgentState` carries only current-step working memory (~30 fields). All persistent context is in MIRIX.
- Agents receive `memory` and `logger` via constructor injection.
- Every agent's entry method updates `AgentState` and calls `memory.update()` with typed packets.
- The `memory_context` field on `AgentState` holds the retrieved MIRIX context string for the current step.
- LLM calls go through `ILLMClient` with structured output (Pydantic models) for observer/decider/reflector.
- `VisualMonitor` (tkinter native floating window, `visual/monitor.py`) shows real-time progress on the host machine during execution. Window: 900×640, topmost, left panel = live device screenshot via `adb exec-out screencap -p` (refresh 1.2s, requires Pillow), right panel = test counter, progress bar, current scenario status, last 3 QA updates. Aliased as `BrowserDashboard` and `TkDashboard`. Controlled by `LIVE_DASHBOARD_ENABLED` env var (default `true`). Pass `device_id` matching `TARGET_DEVICE` for live screen; omit for progress-only mode. Requires: `pip install Pillow`.

## Live Dashboard — visual/monitor.py

`TkDashboard` / `VisualMonitor` is a compact tkinter floating window launched by runner before the batch starts.

### Architecture

```
runner.py
  └── BrowserDashboard.start()    ← spawns tkinter in daemon thread
        ├── left panel: adb screencap → PIL → Canvas (refresh 1.2s)
        └── right panel: queue-driven label/canvas updates

runner pushes via:
  monitor.push_progress(scenario_idx, scenario_total, step_idx, step_total, tcs_id, status)
  monitor.push_log(component, message, detail)   ← filters out OBSERVER/DECIDER/EXECUTOR noise
  monitor.stop()
```

### Files

| File | Role |
|---|---|
| `visual/monitor.py` | Entire dashboard — single file, no external server |
| `visual/dashboard/` | Legacy browser dashboard files (kept, unused) |
| `tests/test_dashboard_live.py` | Standalone demo — run without device or main.py |

### Status: IN PROGRESS

Runner integration (`core/workflow/predefined/runner.py`) patch was applied but needs verification — `_DashboardWrappedExecutor` and `_default_runtime_factory` hooks are in place but have not been tested end-to-end with a real 69-case batch. Dashboard demo (`tests/test_dashboard_live.py`) works standalone.

**Remaining tasks:**
- [ ] Verify `push_progress` calls reach window during actual batch run
- [ ] Test device screenshot rendering with real ADB device (`TARGET_DEVICE`)
- [ ] Tune `_SHOT_INTERVAL` if screencap causes ADB congestion during execution
- [ ] Confirm `monitor.stop()` called cleanly after batch ends / on crash
- [ ] (Optional) Add scenario name / description next to TCS ID in status card
