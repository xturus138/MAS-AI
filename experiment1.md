# Experiment 1: Workflow Comparison Analysis

This document defines the two operational modes implemented in the MAS AI framework to evaluate the efficiency and reliability of different multi-agent coordination strategies.

---

## Mode 1: Predefined Workflow (Scenario-Based)

### 1.1 Architecture
This mode operates on a **Design-Verified Sequential** architecture. It treats the test execution as a predefined sequence of atomic tasks that must match a design prototype.

*   **Logic Source**: `scenario.xlsx`
*   **Knowledge Base**: Figma Prototypes (Nodes & Connections).
*   **Orchestrator Role**: Protocol Manager & Bridge Builder.
*   **Validation**: Visual QA against Figma "Gold Standard" screenshots.

### 1.2 "Truth" Workflow
1.  **Scenario Discovery**: Orchestrator reads `scenario.xlsx`.
2.  **Figma Mapping**: Orchestrator uses LLM/Heuristics to match the `navigation_context` to a specific **Figma Frame ID**.
3.  **Prototype Tracing**: The system traces the `sub_steps` through the Figma Prototype connections to identify the expected **Final Node**.
4.  **Gold Standard Acquisition**: Fetches the screenshot of the identified Final Node from Figma API as the success baseline.
5.  **Execution Loop**:
    *   **Observer**: Captures current UI and produces semantic analysis.
    *   **Decider**: Maps the *current sub-step* instruction to a specific Widget ID.
    *   **Executor**: Performs the ADB action.
    *   **Reflector**: Verifies if the local screen state moved correctly relative to the instruction.
6.  **Final QA**: Compares the final Android screenshot with the Figma Gold Standard.
7.  **Bridge Navigation**: Orchestrator computes the shortest path between the end of Scenario A and the Figma start-node of Scenario B.

---

## Mode 2: Autonomous Workflow (Goal-Based)

### 2.1 Architecture
This mode operates on a **Reactive Planning** architecture. It treats the test execution as an open-ended navigation task where the path is discovered in real-time.

*   **Logic Source**: Scenario Description (treated as a high-level `task_goal`).
*   **Knowledge Base**: Real-time UI analysis (OCR/CV).
*   **Orchestrator Role**: Strategic Planner & Router.
*   **Validation**: Heuristic completion check (is the goal reached?).

### 2.2 "Truth" Workflow
1.  **Goal Initialization**: Converts the scenario description into a primary `task_goal`.
2.  **Planning Loop**:
    *   **Orchestrator (Planner)**: Analyzes the current screen + history + `task_goal` to generate the **Next Concrete Instruction** (e.g., "The search bar is visible, I should click it now").
    *   **Observer**: Provides the semantic map (widgets/text) needed for execution.
    *   **Decider**: Receives the dynamic instruction from the Orchestrator and finds the correct interaction point.
    *   **Executor**: Performs the ADB action.
    *   **Reflector**: Evaluates if the agent is "getting closer" to the high-level goal or if it is stuck.
3.  **Self-Correction**: If the Reflector detects failure, the Orchestrator generates a *new* plan (e.g., "The previous click didn't work, let's try scrolling instead").
4.  **Natural Navigation**: Unlike Mode 1, there is no "Bridge" phase; the agent simply navigates to the next goal as part of its continuous planning logic.

---

## Comparison Metrics for Experiment

| Metric | Predefined (Mode 1) | Autonomous (Mode 2) |
| :--- | :--- | :--- |
| **Success Rate** | High (Path is verified by Figma) | Variable (Depends on UI complexity) |
| **Step Efficiency** | Optimal (Direct path) | Sub-optimal (May explore/backtrack) |
| **Figma Accuracy** | 1:1 Matching | N/A (Exploratory behavior) |
| **Recovery** | Limited (Specific retries only) | High (Can re-plan around obstacles) |
| **Token Cost** | Predictable | Dynamic (Re-planning is expensive) |
