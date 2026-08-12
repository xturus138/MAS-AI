# MAS AI: Multi-Agent Android Testing Framework

> Automated GUI testing for Android apps using multiple AI agents working together.

## What is this?

MAS AI is a research project for my undergraduate thesis (*skripsi*) that explores using multiple AI agents to automatically test Android applications. Instead of writing manual test scripts, the system uses several specialized agents that observe the screen, decide what to do, execute those actions, and check whether they worked.

I built this to compare two approaches to automated testing:
1. Following a script: executing predefined test steps
2. Exploring autonomously: letting the AI figure out how to reach a goal

Both approaches get the same visual perception, so the comparison is about strategy, not raw capability.

## How I built this

I designed and implemented this framework myself as part of my thesis research. I didn't write every line alone though. I used Claude as a coding partner for implementation details, debugging, and code structure, roughly the way you'd use a very well-read pair programmer who never gets tired of your codebase.

Key technologies:
* Python and LangGraph for the multi-agent orchestration
* LangChain for LLM provider abstraction
* ADB (Android Debug Bridge) for device control
* Figma API for design reference
* SQLite and JSON for the memory system

## System overview

The framework runs on your computer and controls an Android device (physical phone or emulator) over ADB. It takes screenshots, analyzes them with AI, decides what to do, and sends touch and type commands back to the device.

### The agent team

Five agents work in a loop: Observer, then Decider, then Executor, then Reflector, then back to Orchestrator.

| Agent | Job |
|-------|-----|
| **Observer** | "What do I see?" Analyzes screenshots and identifies UI elements. |
| **Decider** | "What should I do?" Chooses the next action based on the current goal. |
| **Executor** | "Do it." Translates decisions into actual screen touches and inputs. |
| **Reflector** | "Did it work?" Verifies actions achieved the intended result. |
| **Orchestrator** | "What's next?" Coordinates the overall flow and decides which agent runs next. |

The first four live in `agents/`. The Orchestrator lives in `core/workflow/{mode}/orchestrator.py` instead, because its logic differs quite a bit between predefined mode (a linear step pipeline with retry and bridge-navigation logic) and autonomous mode (LLM-driven routing via `Command(goto=...)`).

### Observer uncertainty (experimental, off by default)

The Observer can optionally run Discrete Semantic Entropy (DSE) measurement: it generates several independent re-interpretations of the same screen and checks how much they agree, as a rough signal of how confident the perception step actually is. This is measurement only. It never changes what the Observer returns, never gates the Decider, Executor, or Reflector, and never produces a pass/fail verdict. It just writes entropy numbers to disk for later analysis.

It's off by default (`OBSERVER_UNCERTAINTY_ENABLED=false`) because it's slow. When enabled, every Observer step in `main.py` blocks until DSE finishes sampling and clustering every widget on screen, which can add minutes per step. See [docs/observer-uncertainty.md](docs/observer-uncertainty.md) for the full design, and `tests/uncertainty_menu.py` for a way to test it in isolation without running the whole framework.

When DSE finds real disagreement between samples, it also writes a short plain-English explanation of what disagreed. That gets printed to the CLI and collected into the "Observer Uncertainty" section of `run_overview.md`.

### Memory system (MIRIX)

The agents remember things across steps through a memory system I call MIRIX, split into six stores:

* **Core memory**: session info like the test goal and expected result
* **Episodic memory**: an event log of everything that happened, in SQLite
* **Semantic memory**: UI element descriptions for cross-test recall
* **Procedural memory**: test step sequences pulled from the Excel file
* **Resource memory**: screenshots and files on disk
* **Knowledge vault**: domain knowledge accumulated across runs

The point of splitting it up this way is to keep the agents' working state small while still letting them pull in richer context when they actually need it.

## Two ways to test

### 1. Predefined mode (script based)

You define test scenarios in an Excel file (`scenario.xlsx`) inside a scenario folder, for example `scenarios/notes/scenario.xlsx`, selected via `SCENARIO_DIR` in `.env`. Each scenario has numbered steps like:
1. Click "Login" button
2. Enter email address
3. Enter password
4. Click submit

The system follows these steps exactly and checks each one against the Figma design reference.

Best for regression testing, acceptance criteria validation, and repeatable test suites.

### 2. Autonomous mode (goal based)

You give the system a high-level goal, something like "add an item to cart and complete checkout," and the agents work out the specific steps by reading the screen as they go. The orchestrator LLM decides the sequence: observe first, execute what the decider planned, or check if the goal is already done.

Best for exploratory testing, robustness checks, and finding UI paths you didn't think to script.

## Why compare these two?

My research question is simple to state and harder to answer: which approach works better for Android GUI testing, following human-written scripts or letting an AI explore on its own?

Both approaches see the same screenshots and UI elements, so the comparison isolates strategy (scripted vs. adaptive) rather than raw capability.

Metrics I track:
* Success rate per test scenario
* Number of actions taken, as a rough measure of efficiency
* First-attempt accuracy, meaning how often it gets things right without retrying
* Widget localization success
* Token usage and cost per scenario

## Project structure

```
MAS AI/
├── agents/              # Observer, Decider, Executor, Reflector, Recorder
├── core/                # Models, ports, workflow runners, utilities
│   ├── models/          # AgentState (LangGraph TypedDict)
│   ├── ports/           # Abstract interfaces (ILLMClient, IDeviceClient)
│   ├── workflow/        # Predefined + autonomous graphs (Orchestrator lives here)
│   ├── uncertainty/     # Observer DSE uncertainty measurement (Phase 1, optional)
│   └── utils/           # LLM factory, pricing, output manager, process logger, etc.
├── memory/              # MIRIX memory system (6 stores)
│   └── retrieval/       # Active retrieval across Episodic + Semantic stores
├── shared/              # Config + LLM prompts (per-agent, few-shot)
├── adapters/            # Device (ADB), LLM (LangChain), Figma
├── tools/               # Executor tools (ADB), observer tools (screenshot/OCR)
├── visual/              # PyQt5 real-time monitoring overlay
├── analysis/            # Run comparison tools
├── scripts/             # Maintenance (cleanup outputs, etc.)
├── tests/               # Pytest suite plus standalone device/API diagnostics
├── scenarios/           # Scenario folders, each with its own scenario.xlsx
│   └── notes/
├── docs/                # Design docs, uncertainty spec, prompting notes
├── main.py              # Entry point
├── PROVIDER_SWITCH.md   # LLM provider quick-switch cheat sheet
└── outputs/             # Test results and artifacts
```

## Quick start

### Prerequisites

1. Android device with USB debugging enabled (or an emulator)
2. ADB installed and device connected
3. Python 3.10+
4. (Optional) Figma access token for design reference

### Setup

```bash
# Install dependencies
pip install -r requirements.txt

# Configure environment
cp .env.example .env
# Edit .env with your API keys and device settings
```

### Run the automated suite

```bash
pip install -r requirements-dev.txt
python -m pytest -q
```

### Run MAS AI

```bash
# Choose mode in .env:
# WORKFLOW_STRATEGY=predefined  (follow scripts)
# WORKFLOW_STRATEGY=autonomous  (goal-driven exploration)

python main.py
```

Results are saved to `outputs/runs/{mode}/{date}/{tcs_id}__{timestamp}/`, with per-step artifacts (screenshots, XML dumps, LLM logs, memory snapshots) under a `steps/NNN/` subfolder.

## Documentation

* [Prompt Engineering Plan](docs/promptingplan.md): how I tuned the LLM prompts for each agent
* [Observer Uncertainty](docs/observer-uncertainty.md): DSE uncertainty measurement design, config, and how to test it standalone
* [Predefined Workflow Diagram Gaps](docs/predefined-workflow-diagram-gaps.md): known differences between the thesis architecture diagram and the actual code

## Research context

This project is part of my undergraduate thesis in Computer Science. I'm trying to get at something practical: what multi-agent AI systems can actually do for mobile testing today, where they fall short, and how different orchestration strategies compare in practice.

If you're a researcher or practitioner interested in AI-assisted testing, feel free to explore the code or reach out. I wrote the research questions and designed the system, but I want to be upfront that Claude helped a lot with the implementation. Managing a codebase this size alone would have been a much slower process without it.

*Built with Python, LangGraph, and help from Claude. Research by Raditya Aryabudhi Ramadhan.*
