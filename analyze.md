**Explanation:**

[cite_start]The SCENGEN framework is designed as an iterative, human-like reasoning process based on the **OODA Loop** (Observe, Orient, Decide, Act)[cite: 75]. [cite_start]It treats GUI testing as a goal-oriented task where multiple specialized agents collaborate through a shared **Context Memory** to bridge the gap between low-level events and high-level business logic[cite: 12, 71, 79].

Below is the rundown of the SCENGEN MAS architecture followed by the adaptation plan for your thesis.

---

### SCENGEN MAS Architecture Rundown

#### 1. Context Memory (The Brain)
[cite_start]Acts as a central repository to overcome the stateless nature of LLMs[cite: 248, 252].
* [cite_start]**Long-term Memory:** Stores static data like device info and scenario descriptions[cite: 253].
* [cite_start]**Working Memory:** Tracks dynamic session data, including the history of executed actions and current goals[cite: 254].
* [cite_start]**Short-term Memory:** Records transient data like the current/previous GUI screenshots and widget recognition results[cite: 255].

#### 2. The Five Specialized Agents
* [cite_start]**Observer (Perception):** Combines Computer Vision (CV) and OCR to detect widgets and layouts[cite: 14, 81, 291]. [cite_start]It interprets the "semantic role" of widgets (e.g., distinguishing a 'submit' button from a 'cancel' button)[cite: 83].
* [cite_start]**Decider (Reasoning):** Uses LLMs to plan the next action based on the target scenario and current GUI state[cite: 15, 85]. [cite_start]It bridges the gap between abstract intent and executable operations[cite: 313].
* [cite_start]**Executor (Action):** A rule-based module that translates the Decider's plan into system-level commands (e.g., Android ADB)[cite: 16, 92, 433].
* [cite_start]**Supervisor (Validation):** Verifies if the action achieved the intended state transition[cite: 16, 96]. [cite_start]It uses an adaptive waiting strategy to handle loading spinners before checking for success[cite: 471, 472].
* [cite_start]**Recorder (Knowledge):** Logs interaction history and monitors for runtime bugs (crashes/exceptions) to update the Context Memory for the next iteration[cite: 17, 100, 103].

---

### Thesis Adaptation: Suitmedia Scenario-Based Testing

[cite_start]Your thesis involves a transition from SCENGEN's **Goal-Oriented** approach (where the LLM decides the steps) to a **Step-Oriented** approach (where the steps are predefined in an XLSX document)[cite: 1016, 1045].

#### Key Changes Required
| Feature | SCENGEN Approach | Your Thesis Approach |
| :--- | :--- | :--- |
| **Input Source** | [cite_start]High-level Natural Language Prompt[cite: 323]. | [cite_start]Structured XLSX Test Case (Steps + Expected Results)[cite: 1045]. |
| **Decision Logic** | [cite_start]LLM reasons "what" to do next based on goal[cite: 315]. | [cite_start]**AI Orchestrator** parses the next "Predefined Step" from XLSX[cite: 1030]. |
| **Verification** | [cite_start]Semantic check by LLM if the "goal" is closer[cite: 496]. | [cite_start]Strict comparison between the UI and the "Expected Result" column[cite: 1031]. |
| **Scale** | [cite_start]Single scenario focus[cite: 541]. | [cite_start]Batch processing of 50-400 test cases[cite: 1019, 1026]. |

---

### Proposed Agent Workflow for Your Thesis

[cite_start]To match your draft's **AI Orchestrator**-centric model, I recommend the following four agents and workflow[cite: 1030, 1031]:

#### 1. AI Orchestrator (The Manager)
* [cite_start]**Role:** Acts as the central controller[cite: 1030].
* [cite_start]**Task:** Parses the XLSX file, extracts the current test step, and manages the "Context Window" to prevent LLM fatigue[cite: 1026, 1042]. It tells other agents which step is currently being executed.

#### 2. Observer Agent (The Eyes)
* [cite_start]**Role:** GUI Understanding[cite: 1031].
* [cite_start]**Task:** Captures the Android XML hierarchy or screenshots[cite: 1031]. It identifies the specific widget mentioned in the "Step" (e.g., if the step says "Click Login," it finds the coordinates for the Login button).

#### 3. Executor Agent (The Hand)
* [cite_start]**Role:** Direct Execution[cite: 1031].
* [cite_start]**Task:** Uses ADB or UIAutomator to perform the action (Click, Type, Swipe) provided by the Orchestrator at the coordinates found by the Observer[cite: 1031].

#### 4. Reflector Agent (The Judge)
* [cite_start]**Role:** Verification & Feedback[cite: 1031].
* [cite_start]**Task:** Compares the "Expected Result" from your XLSX with the new state of the app[cite: 1031]. If the UI matches the expected result, it signals the Orchestrator to move to the next row in the spreadsheet.

#### Workflow Summary:
1.  **Orchestrator** reads Row 1 of the Suitmedia XLSX.
2.  **Observer** scans the current screen to find the target element described in Row 1.
3.  **Executor** performs the action.
4.  **Reflector** checks if the UI now matches the "Expected Result" in Row 1.
5.  **Orchestrator** logs the result and moves to Row 2.

**Sources:**
* Based on "LLM-Guided Scenario-based GUI Testing.pdf" (SCENGEN)
* Based on "Raditya Aryabudhi Ramadhan - Draft Skripsi.pdf" (Thesis Context)