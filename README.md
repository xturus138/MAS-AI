# MAS AI — Multi-Agent Android Testing Framework

> Automated GUI testing for Android apps using multiple AI agents working together.

## What is this?

MAS AI is a research project for my undergraduate thesis (*skripsi*) that explores using multiple AI agents to automatically test Android applications. Instead of writing manual test scripts, this system uses several specialized AI agents that collaborate to observe the screen, decide what actions to take, execute those actions, and verify the results.

I built this framework to compare two different approaches to automated testing:
1. **Following a script** — executing predefined test steps
2. **Exploring autonomously** — letting the AI figure out how to reach a goal

Both approaches use the same visual perception capabilities, so it's a fair comparison of methodology rather than capability.

## How I Built This

**Solo Research Project**: I designed and implemented this entire framework as part of my thesis research. While the codebase is substantial, I didn't write every line alone, so I used Claude (Anthropic's AI assistant) as a coding partner to help with implementation details, debugging, and code structure. Think of Claude as an extremely knowledgeable pair programmer who helped translate my designs into working code.

**Key Technologies**:
* Python + LangGraph for the multi-agent orchestration
* LangChain for LLM provider abstraction
* ADB (Android Debug Bridge) for device control
* Figma API for design reference
* SQLite + JSON for the custom memory system

## System Overview

The framework runs on your computer and controls an Android device (physical phone or emulator) via ADB. It takes screenshots, analyzes them with AI, decides what to do, and sends touch/type commands back to the device.

### The Agent Team

Five specialized agents work in a loop:

| Agent | Job |
|-------|-----|
| **Observer** | "What do I see?" (Analyzes screenshots and identifies UI elements) |
| **Decider** | "What should I do?" (Chooses the next action based on current goal) |
| **Executor** | "Do it" (Translates decisions into actual screen touches and inputs) |
| **Reflector** | "Did it work?" (Verifies actions achieved the intended result) |
| **Orchestrator** | "What's next?" (Coordinates the overall flow and decides which agent runs next) |

### Memory System (MIRIX)

The agents remember things across steps using a structured memory system designed called MIRIX. It has six different "memory stores":

* **Core Memory**: Session info like test goal and expected result
* **Episodic Memory**: Event log of everything that happened (SQLite)
* **Semantic Memory**: UI element descriptions for cross-test recall
* **Procedural Memory**: Test step sequences from the Excel file
* **Resource Memory**: Screenshots and files on disk
* **Knowledge Vault**: Domain knowledge accumulated across runs

This keeps the working state small while allowing rich context retrieval when agents need it.

## Two Ways to Test

### 1. Predefined Mode (Script-Based)

You define test scenarios in an Excel file (`scenario.xlsx`). Each scenario has numbered steps like:
1. Click "Login" button
2. Enter email address
3. Enter password
4. Click submit

The system follows these steps exactly, verifying each one against the Figma design reference.

**Best for**: Regression testing, acceptance criteria validation, repeatable test suites

### 2. Autonomous Mode (Goal-Based)

You give the system a high-level goal like *"Add an item to cart and complete checkout"*. The AI agents figure out the specific steps needed by analyzing the screen in real-time.

The orchestrator LLM decides the sequence: should I observe first? Execute what the decider planned? Check if we're done?

**Best for**: Exploratory testing, robustness evaluation, discovering unexpected UI paths

## Why Compare These Two?

My research question: *Which approach is more effective for Android GUI testing, following human-written scripts or letting an AI explore autonomously?*

Both approaches get the same visual information (screenshots, UI elements), so the comparison isolates the **strategy** (scripted vs. adaptive) rather than **capability** (what the AI can see).

Metrics I track:
* Success rate per test scenario
* Number of actions taken, which indicates efficiency
* First-attempt accuracy (how often it gets things right without retrying)
* Widget localization success
* Token usage and cost per scenario

## Project Structure

```
MAS AI/
├── agents/              # The five agent implementations
├── core/                # Workflow runners and orchestration
├── memory/              # MIRIX memory system stores
├── shared/prompts/      # Optimized LLM prompts (few-shot, CoT, etc.)
├── adapters/            # Device (ADB), LLM, Figma, OmniParser
├── tools/               # Screenshot, OCR, element detection
├── visual/              # PyQt5 real-time monitoring overlay
├── scenario.xlsx        # Test scenarios and steps
├── main.py              # Entry point
└── outputs/             # Test results and artifacts
```

## Quick Start

### Prerequisites

1. Android device with USB debugging enabled (or emulator)
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

### Run Tests

```bash
# Choose mode in .env:
# WORKFLOW_STRATEGY=predefined  (follow scripts)
# WORKFLOW_STRATEGY=autonomous  (goal-driven exploration)

python main.py
```

Results saved to `outputs/{mode}/{scenario_id}_{timestamp}/`

## Documentation

* [Prompt Engineering Plan](docs/promptingplan.md): How I optimized LLM prompts for each agent
* [Memory System](docs/mirix_memory.md): Detailed MIRIX architecture (if migrating from older version)

## Research Context

This project is part of my undergraduate thesis in Computer Science. The goal is to contribute practical insights about multi-agent AI systems for mobile testing, specifically what is possible today, where the limitations are, and how different orchestration strategies compare.

If you're a researcher or practitioner interested in AI-assisted testing, feel free to explore the code or reach out. While I wrote the research questions and designed the system, I gratefully acknowledge Claude's assistance in the implementation, as it has been genuinely helpful for a solo researcher managing a codebase of this scope.

## License

MIT License. See LICENSE file for details.

*Built with Python, LangGraph, and help from Claude. Research by [your name].*
