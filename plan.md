To empirically justify your decision to switch from an AI-driven orchestrator to a predefined workflow, you can conduct a comparative analysis (A/B test) between the two modes. Based on your thesis draft, the ScenGen framework, and multi-agent system literature, here are the specific metrics you should track to build a strong, data-driven justification for your thesis defense:
1. Efficiency and Cost Metrics
These metrics will prove that an AI-driven workflow is overly heavy and expensive for structured test cases, directly supporting your goal of reducing testing time
.
Time Overhead / Average Time per Scenario: Measure the total execution time or "rata-rata waktu per skenario"
. An AI-driven orchestrator adds significant latency because it must reason through every step, whereas a predefined workflow executes steps immediately
.
Token Consumption (Input/Output): Track the total number of tokens used per scenario
. Fully autonomous agents require extensive context windows and multiple LLM calls to decide which agent to invoke next
. A predefined workflow will show a massive reduction in token usage (and therefore API cost)
.
2. Reliability and Stability Metrics
Automated regression testing requires absolute predictability. These metrics will demonstrate that the AI-driven mode introduces unnecessary volatility.
Consistency / Reproducibility: Run the exact same scenario 5 times in both modes. Measure how often the agent produces the exact same sequence of actions
. AI-driven workflows are probabilistic and may choose different routes or tools for the same problem, leading to reproducibility issues
. A predefined workflow will score 100% on consistency.
Retry and Fallback Frequency: Track how often the orchestrator gets stuck, calls the wrong tool, or has to trigger a self-correction loop
. High retry frequencies in the AI-driven mode will highlight its instability compared to a deterministic script.
Abnormal Termination Rate: Measure how often the test generation crashes or terminates without completing the scenario
.
3. Task Success and Accuracy Metrics
These metrics ensure that the system is actually achieving the primary goal of Quality Assurance: correctly executing tests.
Task Success Rate & Coverage Rate: As defined in your thesis and the ScenGen framework, measure the proportion of test generations that successfully complete and fully cover the target scenario
.
Tool Precision and Parameter Accuracy: Evaluate whether the agents called the correct tools with the exact correct parameters (e.g., clicking the right widget, inputting the correct text)
. Autonomous orchestrators sometimes suffer from "tool misselection" when choosing from a large pool of tools, whereas predefined workflows guarantee the correct tool is routed at the correct time
.
Recovery Rate (Dynamic Conditions): Your thesis mentions evaluating the "recovery rate terhadap kondisi dinamis" (recovery rate against dynamic conditions)
. You can measure if the predefined workflow (using tools like the UI stability wait you proposed earlier) handles loading screens and pop-ups just as effectively as the AI-driven mode, proving you don't lose robustness by switching.
How to frame this in your thesis:
You can create a comparison table in your evaluation chapter mapping these metrics. By showing that the Predefined Workflow drastically reduces Token Consumption and Time Overhead while maximizing Consistency and Success Rate, you perfectly align with the core engineering principle mentioned in the literature: "Choose the simplest architecture that effectively addresses your requirements"
. You can conclude that while AI-driven orchestration is powerful for open-ended exploration, predefined workflows provide the auditable, low-latency, and highly consistent execution required for enterprise-grade GUI testing.