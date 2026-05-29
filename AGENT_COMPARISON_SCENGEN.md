# MAS AI vs ScenGen — Agent-by-Agent Comparison

**Context:** ScenGen (Yu et al., 2025 — TU Munich / Nanjing University) is an LLM-guided scenario-based GUI testing framework for Android. MAS AI is a comparative research framework whose core contribution is contrasting two orchestration strategies (Predefined vs Autonomous). The use-cases differ enough that not every ScenGen design choice is worth adopting.

---

## 1. Observer Agent

### ScenGen
- **Stage 1 – CV Detection:** Trained model (bounding-box detection of interactive widgets). Identifies buttons, inputs, lists etc. semantically.
- **Stage 2 – OCR Extraction:** EasyOCR to extract visible text.
- **Stage 3 – Fusion + Filtering:** Merges CV boxes with OCR text, deduplicates overlapping elements, removes status bar noise.
- **Stage 4 – LLM Semantic Interpretation:** Multimodal LLM call on the annotated screenshot to produce a natural-language semantic map.

### MAS AI (`agents/observer_agent.py` + `tools/observer_tools.py`)
| Layer | Implementation | Gap vs ScenGen |
|---|---|---|
| CV Stage 1 | OpenCV Canny edge detection (50/150 thresholds) + contour area filtering | Classical, NOT a trained model. No semantic class labels. |
| OCR Stage 2 | EasyOCR, confidence ≥ 0.4, scaled to 1080px | Equivalent |
| Fusion Stage 3 | `_merge_ocr_blocks` (y-overlap + 40px horizontal gap) → `_group_keyboard_elements` (50% screen height threshold) → `_merge_and_filter` (IoU matching, proximity < 25px, orphaned OCR → `text_stub`, sequential integer IDs) | Arguably more detailed than ScenGen's description |
| LLM Semantic | Multimodal LLM call on annotated screenshot → full natural-language UI description | Equivalent |
| Stagnation detection | `_detect_stagnation`: compares current summary against last episodic entry | Extra — ScenGen doesn't have this |

**Gap summary:** Stage 1 only. Canny detects visual boundaries but produces unlabeled blobs. A trained model (e.g., OmniParser, UIED, ScreenRecognition) would assign semantic class labels (`button`, `input`, `icon`) directly, reducing false positives and improving widget ID precision.

### Recommendation
**Implement:** Replace `detect_visual_elements` (Canny) with **OmniParser** as Stage 1. The branch `experiment/omniparser-observer` is already named for this. OmniParser produces icon descriptions + bounding boxes from a screenshot, which slots directly into the existing `_merge_and_filter` pipeline.

**Do not implement:** ScenGen's exact CV model is not public. OmniParser is a better fit because it handles icon semantics (something Canny completely misses) and is pre-trained on general UI screenshots.

---

## 2. Decider Agent

### ScenGen — 2-Stage Design
1. **Logical Decision:** LLM selects the next action type and identifies the target widget by description.
2. **Widget Localization:** Maps the widget description back to a specific screen coordinate.
   - **Widget Prediction Fallback:** If the target widget is not found, LLM predicts its likely position from context (partial match, adjacent elements, or scroll-to-reveal inference).
3. **Self-correction loop:** If widget localization fails twice, Decider asks Observer to re-scan before retrying.

### MAS AI (`agents/decider_agent.py`)
- Single-stage structured output (`ActionPlan` Pydantic model): action type + `target_id` (integer widget ID from Observer) + payload.
- Widget resolution happens in **ExecutorAgent** (ID → bounds → coordinates).
- On lookup failure: logs `widget_lookup_fail` counter, writes `ERROR: Target ID X not found` as `execution_result`, and continues to Reflector (which will return `passed=False`).

**Gap summary:**
| Feature | ScenGen | MAS AI |
|---|---|---|
| Widget lookup failure recovery | Widget Prediction fallback (LLM inference) | Fails gracefully, increments counter, Reflector retriggers |
| Self-correction | Decider → re-observe loop | Reflector fail → Orchestrator re-plans → Observer re-scan |
| Separation of logic vs localization | 2 separate prompts | 1 combined prompt |

### Recommendation
**Do not implement the 2-stage split.** The Orchestrator already handles recovery when Reflector returns `passed=False`. Adding a second LLM call inside Decider for localization doubles token cost at every step without improving the research metric (widget_localization_effectiveness is already tracked via `widget_lookup_success / (success + fail)`).

**Partial implementation worth considering:** Widget Prediction fallback as a narrow patch inside `ExecutorAgent`. When `target_id` is not found in `widgets`, before writing `ERROR`, attempt a text-match fallback (search widgets by `text` field containing the Decider's `intent` keywords). This is zero extra LLM calls and recovers many "widget not found" errors caused by minor Observer ID drift between steps.

---

## 3. Executor Agent

### ScenGen
- Executes ADB actions (tap, input, scroll, back).
- **Explicit rendering delay** (waits for Activity transitions).
- **Post-action screenshot** for state verification.
- **ADB logcat crash monitoring:** After each action, reads logcat for crash signatures (`FATAL EXCEPTION`, `ANR`, `NullPointerException`) and marks the step as failed if a crash is detected.

### MAS AI (`agents/executor_agent.py`)
| Feature | Status |
|---|---|
| ADB action dispatch | Fully implemented (click, long_click, input, scroll, press_back, press_home, press_enter, start_app) |
| Rendering delay | `time.sleep(3)` — comment in code explicitly references ScenGen pattern |
| Post-action screenshot | Captures `post_action.png`, updates `screenshot_path` in state and MIRIX Resource store |
| ADB logcat crash monitoring | **Missing** |

**Gap summary:** Crash detection. If the app crashes after an action, the post-action screenshot shows an Android crash dialog or blank screen. Reflector can detect this visually, but it takes a full LLM call. ADB logcat gives the same signal in milliseconds for free.

### Recommendation
**Implement:** Add a narrow crash check at the end of `execute()` before returning, using `adb -s <device> logcat -d -t 50 *:E` filtered for crash keywords. If a crash signature is found, prepend `"[CRASH]"` to the `execution_result` string. This is a 2-line ADB call with no LLM cost, and it makes the `tool_precision_rate` metric more accurate.

**Do not implement:** Full logcat streaming (real-time monitoring). That requires a background thread, complex synchronization, and produces noisy output. The post-action point-in-time logcat dump is sufficient.

---

## 4. Reflector Agent (MAS AI) / Supervisor (ScenGen)

### ScenGen — Structured 3-Stage Supervisor
1. **Loading Verification:** Did the UI finish loading? (detects spinners, progress bars, blank screens)
2. **State Transition Verification:** Did the UI change in response to the action? (compares before/after screenshot)
3. **Test Completion Verification:** Does the current state satisfy the test case's expected result?

Each stage is a separate LLM call with a specific prompt. Fails at Stage 1 or 2 trigger a retry before escalating.

### MAS AI (`agents/reflector_agent.py`)
- **Intermediate steps:** Single LLM call — "did the UI change successfully?"
- **Final step:** 2-way or 3-way verification — expected result text + optional Figma Gold Standard comparison.
- Figma discrepancies logged to `figma_comparison_result.json`.
- Metrics: `reflector_first_pass_count`, `reflector_pass_count`, `total_first_verify_calls`.

**Gap summary:**
| Stage | ScenGen | MAS AI |
|---|---|---|
| Loading detection | Explicit Stage 1 | Implicit — LLM observes spinner/blank as failure |
| State transition | Explicit Stage 2 (screenshot diff) | Implicit — LLM observes unchanged UI as failure |
| Goal satisfaction | Explicit Stage 3 | Explicit (final step verification) |
| Figma design comparison | Not present | Present (final step, Gold Standard b64) |

### Recommendation
**Do not split into 3 separate LLM calls.** Each call adds token cost and latency. The current single-call approach where the LLM holistically evaluates loading + transition + goal is adequate for our test cases (UI interactions with clear pass/fail states).

**Worth adding:** An explicit pixel-diff pre-check before calling the LLM. If `post_action.png` and the previous screenshot are more than N% identical (OpenCV `cv2.absdiff`), immediately set `passed=False` and skip the LLM call. This saves one LLM call on every stagnated step, which is where most token waste occurs.

---

## 5. Recorder Agent

### ScenGen — Mid-Cycle Active Recorder
- **Runs after EVERY Executor action**, not at the end.
- Writes action results + screenshot references to a shared context memory (ScenGen's equivalent of episodic store).
- Reads ADB logcat entries and classifies them (info, warning, crash).
- Maintains a running narrative that the Supervisor uses for its Stage 2 verification.

### MAS AI (`agents/recorder_agent.py`)
- **Passive end-of-run finalizer.** Not a LangGraph node.
- Called once by the runner: `recorder.finalize_run_metrics(final_state)`.
- Dumps all episodic memory to `chat_logs.txt`, writes `final_metrics.json` and `interaction_script.json`.
- MIRIX `memory.update()` in each agent handles mid-cycle context persistence (this replaces ScenGen's mid-cycle Recorder for state tracking).

**Gap summary:** The MIRIX design already covers ScenGen's mid-cycle context writing — every agent calls `self.memory.update({"episodic": {...}})` immediately after acting, which is equivalent. The only genuine gap is logcat classification (which is partly covered by the crash detection recommendation above for ExecutorAgent).

### Recommendation
**Do not move Recorder to mid-cycle.** The MIRIX `memory.update()` pattern already achieves the same context persistence. Moving Recorder mid-cycle would just duplicate what the episodic store does.

**Do not implement** logcat classification in Recorder. It belongs closer to the action that could cause the crash (ExecutorAgent), not in the post-run logger.

**Worth adding:** A `record_step()` method on RecorderAgent that takes a single `AgentState` snapshot and appends a row to a `step_trace.csv` file after each cycle. This creates a tabular timeline that's easier to analyze in Excel/Pandas than the full `chat_logs.txt`.

---

## 6. Orchestrator (MAS AI only)

### ScenGen
ScenGen does not have an Orchestrator agent. It has a fixed pipeline: Observer → Supervisor → Decider → Executor, repeated per test step. Scenario steps come from a predefined list.

### MAS AI
Two distinct Orchestrators that are the core research contribution:
- **PredefinedOrchestrator:** Follows `sub_steps` from `scenario.xlsx` in strict index order. Maps steps to Figma nodes. Computes bridge navigation between scenarios.
- **AutonomousOrchestrator:** LLM plans the next agent to call based on task_goal, recent episodic history, and the current observer analysis. No fixed step sequence. Kill switches for loop detection (3 identical consecutive calls) and global step limit (35).

**No gap vs ScenGen.** The Orchestrator is MAS AI's differentiating design, not something ScenGen models. It IS the research question being studied.

**Recommendation:** No changes to Orchestrator design from ScenGen comparison. The most useful improvement here would be more granular kill-switch reasoning logged to MIRIX episodic memory (currently only logs the trigger, not the call pattern that caused it).

---

## Summary Table

| Agent | Gap vs ScenGen | Implement? | Priority |
|---|---|---|---|
| Observer — Stage 1 CV | Canny vs trained model (no semantic labels) | **Yes** — OmniParser | High |
| Decider — 2-stage split | Missing Widget Prediction fallback | Partial — text-match fallback in ExecutorAgent only | Low |
| Executor — crash detection | No ADB logcat crash monitoring | **Yes** — point-in-time logcat dump after each action | Medium |
| Reflector — 3-stage split | Loading/transition check is implicit, not explicit | **No** — current single-pass is sufficient | — |
| Reflector — pixel diff pre-check | No diff-before-LLM optimization | **Yes** — small win on stagnation steps | Low |
| Recorder — mid-cycle | Passive vs active; MIRIX covers context persistence | **No** — MIRIX already solves this | — |
| Recorder — step_trace.csv | No tabular step timeline | Optional — useful for post-run analysis | Low |
| Orchestrator | No ScenGen equivalent | **No change** — this IS the research contribution | — |

---

## What NOT to Implement (and Why)

| Feature | Reason to skip |
|---|---|
| Vector embeddings (FAISS/ChromaDB) | FTS5 is sufficient for structured GUI test vocabulary. 5–10 unique keywords per test step. Vector overhead not justified. |
| 2-stage Decider (full ScenGen design) | Doubles LLM calls per step. Recovery already handled by Orchestrator + Reflector loop. |
| Full 3-stage Reflector | 3× LLM calls for verification. Research metrics don't require stage-level granularity. |
| Real-time logcat streaming | Background thread complexity, noisy output. Point-in-time dump at post-action is enough. |
| ScenGen Recorder mid-cycle | MIRIX `memory.update()` per agent already achieves the same. Redundant. |

---

## Prioritized Implementation Roadmap

1. **OmniParser (Observer Stage 1)** — highest impact. Improves widget ID accuracy, which cascades to better Decider and Executor precision. Already scoped to `experiment/omniparser-observer` branch.
2. **Executor ADB crash detection** — 10 lines of code, zero LLM cost, improves `tool_precision_rate` accuracy.
3. **Reflector pixel-diff pre-check** — reduces token waste on stagnation steps, which are the most expensive part of a failed run.
4. **Executor text-match fallback** — partial Widget Prediction for the common case where ID drift is the only cause of failure.
5. **Recorder step_trace.csv** — nice-to-have for thesis data analysis, doesn't affect runtime.
