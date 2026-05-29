# MAS AI — Multi-Agent Android Testing Framework

A multi-agent system (MAS) for automated Android GUI testing, built with LangGraph. This framework supports fair comparative orchestration, enabling robust evaluation between predefined scripts and autonomous, LLM-driven task completion.

---

## Architecture & Modes

This framework operates on a **Shared Variable Experiment Model**, giving both workflows the exact same visual context and data baseline to perform operations.

### 1. Predefined Workflow (Scenario-Based)
- **Logic**: Strict index-based execution of sub-steps defined in `scenario.xlsx`.
- **Goal**: High reliability and precise regression verification against designers' intent.
- **Key Flow**: `Figma Discovery → Step-by-Step Execution → Visual QA → Bridge Navigation`.

### 2. Autonomous Workflow (Goal-Based)
- **Logic**: Dynamic real-time planning based purely on the `task_goal` and live UI analysis.
- **Goal**: Robustness and unstructured exploratory testing.
- **Key Flow**: `Figma Discovery → Dynamic Planning → Execution → Progress Check → Re-plan`.

---

## Memory System: MIRIX

### Overview

MAS AI uses the **MIRIX** (Multi-agent Intelligent Reasoning and Integration eXperience) memory architecture as its persistent cognitive layer. MIRIX is a structured memory model that separates agent knowledge into specialized stores, each serving a distinct cognitive function — analogous to how human memory separates episodic recollection, semantic knowledge, and procedural skills.

Rather than storing context in the LangGraph state (which inflates every message and bloats token usage), MIRIX externalizes memory to SQLite and JSON stores on disk. The `AgentState` TypedDict becomes a slim **working-memory** object carrying only the values needed for the current cycle step. All scenario context, history, and reference data live in MIRIX and are fetched on demand.

### Memory Stores

MIRIX is composed of six specialized stores managed by a single `MIRIXMemorySystem` meta-manager:

| Store | Backend | What It Holds |
|---|---|---|
| **Core Memory** | JSON file | Session identity, scenario goal, expected result, test type, Figma flags — the immutable facts of a run |
| **Episodic Memory** | SQLite + FTS5 | Timestamped event log of every agent action (observer analysis, executor result, reflector verdict, orchestrator decision) — queryable by actor, step, or keyword |
| **Semantic Memory** | SQLite + FTS5 | Extracted UI concepts and widget descriptions stored as embedding-free semantic facts — used for cross-step UI recall |
| **Procedural Memory** | JSON file | Ordered sub-step sequences loaded from `scenario.xlsx` — the "how to" knowledge for predefined mode |
| **Resource Memory** | JSON + disk | Binary and path-indexed assets (Figma gold standard screenshot, annotated screenshots) — decouples large data from the state graph |
| **Knowledge Vault** | JSON file | Domain-level heuristics and test patterns accumulated across runs — currently populated from scenario metadata |

### How It Works

#### Initialization (`memory.init_session`)

At the start of every scenario, the runner calls `memory.init_session(scenario, tcs_id, figma_context)`. This:
1. Writes immutable facts to **Core Memory** (`task_goal`, `expected_result`, `test_type`, `figma_enabled`, etc.).
2. Writes the ordered test steps to **Procedural Memory** under the `tcs_id` key.
3. Decodes and saves the Figma Gold Standard image to **Resource Memory** on disk.
4. Seeds the **Knowledge Vault** with scenario metadata.

#### Active Retrieval (`memory.retrieve`)

Before every LLM call, each agent calls `memory.retrieve(topic)` with a short query string (e.g., `"execution result step=5"`). The meta-manager fans this query out in parallel across Episodic and Semantic stores using `ThreadPoolExecutor`. Results are tagged and concatenated into a structured context string that is injected directly into the agent's prompt, giving the LLM grounded, recent history without manual state threading.

```
[EPISODIC]  step=5 [executor] action_executed: Tapped Login button — SUCCESS
[EPISODIC]  step=5 [reflector] reflector_evaluation: PASSED: Login screen transition confirmed
[SEMANTIC]  login_button: bottom-center interactive element, id=12
```

#### Memory Updates (`memory.update`)

After each LLM call or execution, agents call `memory.update(packet)` with a typed payload dict. The meta-manager routes each key to the correct store in parallel:

```python
memory.update({
    "episodic": {"event_type": "action_executed", "summary": "...", "actor": "executor", "step": 5},
    "semantic": [{"concept": "login_button", "description": "..."}],
    "resource": {"screenshot_path": "/outputs/.../step_5/after.png"},
})
```

#### Figma Gold Standard

The Reflector Agent retrieves the Figma reference image via `memory.resource.get_figma_gold_b64()` — no base64 string is ever carried in `AgentState`. On the final step of a scenario, the reflector performs a **3-way verification**: live screenshot vs. expected result text vs. Figma Gold Standard image.

---

## What Changed: Before vs. After MIRIX

### Before MIRIX

Prior to MIRIX, all shared context was carried **directly in `AgentState`** — the LangGraph TypedDict that flows as a message through every graph edge on every cycle. This meant:

- Every step passed the full scenario description, all sub-steps, action history, chat logs, reflector reasoning, Figma base64 image, and UI element summaries as fields in the state object.
- Each agent re-read and re-passed these fields even when they didn't change.
- Removal of old fields or addition of new ones required updating the TypedDict, all agents, all orchestrators, and both runners simultaneously.
- Context window usage grew proportionally with scenario length, action count, and UI complexity.
- The `RecorderAgent` ran as a **mid-cycle LangGraph node** every step, adding overhead and complexity to the graph topology.

`AgentState` before MIRIX had approximately **60 fields**, including:
`navigation_context`, `scenario_desc`, `test_type`, `user_role`, `sub_steps`, `task_goal`, `expected_result`, `action_history`, `chat_logs`, `reflector_reasoning`, `orchestrator_reasoning`, `previous_ui_summary`, `previous_screenshot_path`, `annotated_screenshot_path`, `figma_enabled`, `figma_start_node_id`, `figma_end_node_id`, `figma_end_screenshot_b64`, `figma_bridge_steps`, `ui_elements_summary`, `ocr_result`, `detected_elements`, and more.

### After MIRIX

`AgentState` is now a **slim working-memory object of ~30 fields** — only the values that are actively changing within the current cycle step:

- Scenario facts (`task_goal`, `expected_result`, `sub_steps`) live in **Core** and **Procedural Memory**.
- Action history lives in **Episodic Memory** and is retrieved on demand, not carried forward.
- The Figma Gold Standard image lives in **Resource Memory** on disk.
- `AgentState` carries only: control fields (`tcs_id`, `session_id`, `sender`, `current_step`, `is_completed`), current-step working values (`screenshot_path`, `action_plan`, `execution_result`, `widgets`), orchestrator signals (`orchestrator_instruction`, `is_final_step`, `step_retry_count`), stagnation counters, and research metric accumulators.
- A single new field `memory_context: str` carries the retrieved MIRIX context into the current agent call.
- The `RecorderAgent` is **no longer a graph node**. It is called once at the very end of a run by the runner via `recorder.finalize_run_metrics(final_state)`.

### Impact Summary

| Dimension | Before | After |
|---|---|---|
| `AgentState` field count | ~60 | ~30 |
| Scenario context in state | Yes — repeated every cycle | No — stored once in MIRIX |
| Action history in state | Yes — grows unbounded | No — queried from Episodic store |
| Figma image in state | Yes — base64 string in state | No — file on disk, fetched by reflector |
| RecorderAgent position | Mid-cycle graph node | Post-run function call |
| Cross-step recall mechanism | Re-passing stale state fields | Active retrieval via `memory.retrieve()` |
| Memory coupling | Agents read directly from state | Agents read from MIRIX, write update packets |
| Process observability | `print()` statements only | Structured `process.log` per scenario |

---

## Process Logging

Every run writes a **`process.log`** file to the scenario's output directory (`outputs/{mode}/{tcs_id}_{timestamp}/process.log`). The log captures the complete execution trace from start to finish without gaps.

### Log Structure

Each entry follows a fixed-width timestamped format:

```
[2026-05-29 14:32:01.123]  [RUNNER        ]  Graph execution started
                                              recursion_limit=150
[2026-05-29 14:32:01.456]  [ORCHESTRATOR  ]  → Dispatching step 1/5
                                              Click the Login button
[2026-05-29 14:32:02.001]  [OBSERVER      ]  LLM call started (vision pipeline)
                                              instruction=Click the Login button
[2026-05-29 14:32:04.312]  [OBSERVER      ]  LLM call complete
                                              analysis=Login screen visible. 3 input fields...
[2026-05-29 14:32:04.500]  [EXECUTOR      ]  Widget resolved: id=12 → (540, 1200)
                                              text=Login
[2026-05-29 14:32:05.001]  [EXECUTOR      ]  ADB result: OK — tap (540, 1200)
[2026-05-29 14:32:06.200]  [REFLECTOR     ]  Verdict: PASSED
                                              reasoning=Screen transitioned to Home Dashboard...
[2026-05-29 14:32:06.201]  [RUNNER        ]  Graph execution completed
                                              status=SUCCESS  cycles=5
```

### What Gets Logged Per Component

| Component | Events Captured |
|---|---|
| **Runner** | Scenario start (tcs_id, session_id, mode), Figma discovery start/complete (node IDs), graph start, graph end (status, cycles, stagnation count) |
| **Orchestrator** | `━━ CYCLE N ━━` section header, sender context, step dispatch instruction (predefined) or LLM judgment (autonomous), retry/abort/kill-switch decisions |
| **Observer** | Memory retrieval result, screenshot captured, vision pipeline element counts, widget set size, annotated screenshot path, LLM call start + first 500 chars of analysis, stagnation detection outcome |
| **Decider** | Current instruction, memory context retrieved, LLM call start, resolved action plan (type, intent, target widget, text payload) |
| **Executor** | Action type/intent/target_id, widget coordinate resolution, widget lookup failures, ADB result (OK/FAIL), post-action screenshot path |
| **Reflector** | Verification mode (STEP or FINAL + Figma label), instruction + expected result, verdict (PASSED/FAILED), full reasoning, Figma discrepancies |
| **Recorder** | Final metrics snapshot (status, cycles, physical actions, tokens, duration, tool precision rate), log file closed |

---

## Post-MIRIX Workflow: Step-by-Step

The following describes the complete execution sequence after MIRIX integration for a single scenario.

### Startup (Once Per Run)
1. `ADBAdapter` connects to the target device.
2. `ObserverTools` and `ExecutorTools` wrap the device adapter for agent use.
3. `FigmaAdapter` is constructed from the Figma access token (optional — degrades gracefully if unavailable).
4. All scenarios are loaded from `scenario.xlsx` via `load_scenarios()`.

### Per-Scenario Loop

**Step 1 — Bootstrap**
- `MIRIXMemorySystem` is instantiated with a unique `session_id` and `output_dir`.
- `ProcessLogger` is instantiated; writes a header and scenario-start entry to `process.log`.
- LLM clients are created per role via `LLMFactory` (observer, decider, reflector, orchestrator).
- All agents are constructed, each receiving both `memory` and `logger`.

**Step 2 — Figma Discovery**
- The Orchestrator calls `pre_scenario_discovery()`, which uses an LLM to trace the expected path through the Figma prototype graph.
- Returns a `figma_context` dict: `figma_enabled`, `figma_start_node_id`, `figma_end_node_id`, `figma_end_screenshot_b64`.
- The composite Gold Standard image is saved to `output_dir/figma_gold_standard.png`.

**Step 3 — Memory Initialization**
- `memory.init_session(scenario, tcs_id, figma_context)` writes all immutable facts to MIRIX stores.
- Figma Gold Standard base64 is decoded and saved to `output_dir/memory/figma_end.png` by Resource Memory.

**Step 4 — Graph Execution**

The LangGraph state machine runs until `is_completed=True` or a kill-switch fires:

```
START
  └─► ORCHESTRATOR ──────────────────────────────────────────────┐
        │  (reads sub_steps from Procedural Memory)               │
        │  (reads recent episodes from Episodic Memory)           │
        ▼                                                          │
      OBSERVER                                                     │
        │  (takes screenshot, runs vision pipeline)               │
        │  (retrieves semantic context from MIRIX)                │
        │  (writes observer_analysis + semantic facts to MIRIX)   │
        ▼                                                          │
      DECIDER                                                      │
        │  (reads sub_step instruction from Procedural Memory)    │
        │  (retrieves recent history from Episodic Memory)        │
        │  (writes action_plan + episodic entry to MIRIX)         │
        ▼                                                          │
      EXECUTOR                                                     │
        │  (resolves widget ID → coordinates)                     │
        │  (sends ADB tap/swipe/type command)                     │
        │  (writes execution result to Episodic + Resource)       │
        ▼                                                          │
      REFLECTOR                                                    │
        │  (retrieves expected_result from Core Memory)           │
        │  (retrieves Figma Gold from Resource Memory on final)   │
        │  (writes verdict to Episodic Memory)                    │
        └─────────────────────────────────────────────────────────┘
             (PASSED → advance / FAILED → retry via Orchestrator)
```

- **Predefined mode**: Orchestrator advances `current_sub_step_index` on PASS, retries on FAIL (max 3), ends when all steps are verified.
- **Autonomous mode**: Orchestrator LLM judges next action (`OBSERVE / DECIDE / EXECUTE / VERIFY / COMPLETE`) using real-time episodic history and optional Figma reference. Kill switches stop loops of 3 identical calls or runs exceeding 35 cycles.

**Step 5 — Finalization**
- `recorder.finalize_run_metrics(final_state)` is called once after the graph exits.
- Writes `final_metrics.json`, `chat_logs.txt`, and `interaction_script.json` to `output_dir`.
- Reads token/cost totals from LLM log files under `outputs/llm_logs/{session_id}/`.
- Calls `memory.close()` to flush and release all SQLite connections.
- `ProcessLogger.close()` writes the closing footer.

---

## Core Features

- **Figma Integration**: Automatically pulls prototype transitions to synthesize a "Gold Standard" screenshot used for truth verification.
- **Smart Re-Routing (Bridge)**: Dynamically computes navigation steps to bridge the app from its current state to the start state of the next scenario (predefined mode only).
- **Self-Correction**: The **Reflector Agent** sanity-checks results after every step, triggering iterative recovery if a navigation fails.
- **MIRIX Memory**: Structured 6-store memory system separating episodic, semantic, procedural, resource, core, and knowledge vault concerns — enables active retrieval without bloating the LangGraph state.
- **Process Logging**: Full structured execution trace written to `process.log` in every scenario output directory.
- **Cost Observability**: Real-time dollar cost tracking for multi-provider LLM payloads (Google, Anthropic, OpenAI, DeepSeek, etc.).

---

## Data Collection & Metrics

Every test run generates highly granular diagnostic payloads in the output directory:

```
outputs/{mode}/{tcs_id}_{timestamp}/
├── process.log                  ← Full structured execution trace (MIRIX)
├── final_metrics.json           ← Success status, efficiency, design fidelity
├── chat_logs.txt                ← Full episodic event history from MIRIX
├── interaction_script.json      ← Executor-only action sequence
├── figma_gold_standard.png      ← Composite Figma reference image
├── memory/
│   ├── core.json                ← Core Memory store
│   ├── procedural.json          ← Procedural Memory store
│   ├── resource.json            ← Resource Memory index
│   ├── knowledge_vault.json     ← Knowledge Vault store
│   ├── episodic.db              ← Episodic Memory (SQLite)
│   ├── semantic.db              ← Semantic Memory (SQLite)
│   └── figma_end.png            ← Figma Gold Standard image
└── step_{N}/
    ├── screenshot.png           ← Raw device screenshot
    ├── annotated.png            ← Element detection overlay
    ├── action_plan.json         ← Decider reasoning + chosen action
    └── reflector_report.json    ← Reflector verdict + Figma discrepancies
```

### Research Metrics (`final_metrics.json`)

| Metric | Description |
|---|---|
| `status` | `SUCCESS`, `FAILED`, or `STAGNATED` |
| `total_cycles` | Total LangGraph steps executed |
| `physical_actions` | Number of actual ADB interactions (tap, swipe, type) |
| `tool_precision_rate` | Ratio of successful executor actions to total |
| `total_tokens_estimate` | Cumulative LLM token usage across all agents |
| `total_price_usd` | Total LLM cost in USD |
| `total_duration_seconds` | Wall-clock run time |
| `figma_verified` | Whether Figma Gold Standard was used for final verification |
| `research_metrics.coverage_rate` | Steps completed / total defined steps (predefined) |
| `research_metrics.decision_accuracy_initial_acc1` | First-attempt verification pass rate |
| `research_metrics.widget_localization_effectiveness` | Widget ID → coordinate resolution success rate |

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

### 5. Diagnostics
```bash
python check_figma_connection.py   # Test Figma API connectivity
python check_models.py             # Verify LLM provider connectivity
python clean_outputs.py            # Clear outputs directory
```
