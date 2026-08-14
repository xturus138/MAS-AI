# MAS AI — Provider Quick-Switch Guide

Copy-paste the block you want into `.env` to swap all 4 agents at once.

## Bayesian test-selection context — still open

These provider settings do not implement or validate Bayesian Optimization
(BO). The separate BO test-selection idea is still a research question: it
would need real execution outcomes, sequential feedback, and an undecided
coverage-first or cold-start policy before it could affect the multi-agent
workflow. Do not infer AI credit savings from a provider choice; token and
credit cost are not yet measured reliably for that experiment. See
`Hasil AI/JAIST/EXPERIMENT_HYPOTHESIS_BO_QA_TEST_REDUCTION.md` in the research
document workspace for the current hypothesis and open questions.

## Current 69-case baseline scope

Provider switching must not change the immediate goal: run every Firebase Chat
QA case in workbook order through the predefined workflow, preserving state
between cases where possible and recovering navigation only when necessary.
This is a full-suite baseline, not a BO implementation or test-case reduction.

For this run, DSE must remain off:

```bash
OBSERVER_UNCERTAINTY_ENABLED=false
```

The final Excel report must keep the original schema. The runner may populate
only the existing execution fields (`Time Testing`, `Testing Status`, first
`Updated At`, `Testing By`, `OK Evid.`, and `Issue Status`) and must not add
columns or write to developer-tracking fields. Provider-reported token/cost
figures may be kept in artifacts when available, but must not create new Excel
columns or be described as BO credit savings.

**Observer requirement (2026-07-29):** `OBSERVER_DETECTION_METHOD` defaults to
`"llm"` — the Observer now sends the screenshot straight to `OBSERVER_MODEL`
for widget grounding via `with_structured_output(...)`, not just semantic
interpretation. Whatever you set `OBSERVER_MODEL`/`OBSERVER_PROVIDER` to must
support **vision input + reliable structured/function-calling output**
(validated against Gemini). If you swap Observer to a text-only or
function-calling-unreliable model, either verify grounding still works or set
`OBSERVER_DETECTION_METHOD=cv_ocr` to fall back to the classical Canny+OCR
pipeline, which has no such requirement. Decider/Reflector/Orchestrator are
unaffected by this constraint.

## Gemini (Google AI Studio / Developer API — free tier available)

```bash
OBSERVER_PROVIDER=gemini
OBSERVER_MODEL=gemini-3.1-pro-preview
DECIDER_PROVIDER=gemini
DECIDER_MODEL=gemini-2.5-flash
REFLECTOR_PROVIDER=gemini
REFLECTOR_MODEL=gemini-2.5-flash
ORCHESTRATOR_PROVIDER=gemini
ORCHESTRATOR_MODEL=gemini-3.1-pro-preview
```
**Requires:** `GEMINI_API_KEY` in `.env`

---

## Vertex AI (Google Cloud — uses ADC / service account)

```bash
OBSERVER_PROVIDER=vertex
OBSERVER_MODEL=gemini-2.5-flash
DECIDER_PROVIDER=vertex
DECIDER_MODEL=gemini-2.5-flash
REFLECTOR_PROVIDER=vertex
REFLECTOR_MODEL=gemini-2.5-flash
ORCHESTRATOR_PROVIDER=vertex
ORCHESTRATOR_MODEL=gemini-2.5-flash
```
**Requires:** `GOOGLE_APPLICATION_CREDENTIALS=vaultkey/<file>.json` in `.env`

---

## Azure OpenAI

```bash
OBSERVER_PROVIDER=azure
OBSERVER_AZURE_DEPLOYMENT=<your-deployment-name>
DECIDER_PROVIDER=azure
DECIDER_AZURE_DEPLOYMENT=<your-deployment-name>
REFLECTOR_PROVIDER=azure
REFLECTOR_AZURE_DEPLOYMENT=<your-deployment-name>
ORCHESTRATOR_PROVIDER=azure
ORCHESTRATOR_AZURE_DEPLOYMENT=<your-deployment-name>
```
**Requires:** `AZURE_OPENAI_KEY` + `AZURE_OPENAI_ENDPOINT` in `.env`

---

## Blackbox

```bash
OBSERVER_PROVIDER=blackbox
OBSERVER_MODEL=blackboxai/anthropic/claude-opus-4.6
DECIDER_PROVIDER=blackbox
DECIDER_MODEL=blackboxai/anthropic/claude-sonnet-4.6
REFLECTOR_PROVIDER=blackbox
REFLECTOR_MODEL=blackboxai/anthropic/claude-sonnet-4.6
ORCHESTRATOR_PROVIDER=blackbox
ORCHESTRATOR_MODEL=blackboxai/anthropic/claude-opus-4.6
```
**Requires:** `BLACKBOX_API_KEY` in `.env`

---

## 9Router (local MAS-AI model)

```bash
OBSERVER_PROVIDER=9router
OBSERVER_MODEL=MAS-AI
DECIDER_PROVIDER=9router
DECIDER_MODEL=MAS-AI
REFLECTOR_PROVIDER=9router
REFLECTOR_MODEL=MAS-AI
ORCHESTRATOR_PROVIDER=9router
ORCHESTRATOR_MODEL=MAS-AI
```
**Requires:** 9Router server running on `http://localhost:20128`

---

## Alibaba Cloud MaaS

```bash
OBSERVER_PROVIDER=alibaba
OBSERVER_MODEL=qwen-max
DECIDER_PROVIDER=alibaba
DECIDER_MODEL=qwen-max
REFLECTOR_PROVIDER=alibaba
REFLECTOR_MODEL=qwen-max
ORCHESTRATOR_PROVIDER=alibaba
ORCHESTRATOR_MODEL=qwen-max
```
**Requires:** `ALIBABA_API_KEY` in `.env`

---

## Qwen (Alibaba DashScope — International)

Get an API key at https://home.qwencloud.com/api-keys. One key works against
two different endpoint shapes — pick whichever `*_PROVIDER` matches how you
want LangChain to talk to it:

**OpenAI-compatible endpoint:**

```bash
OBSERVER_PROVIDER=qwen
OBSERVER_MODEL=qwen3.8-max
DECIDER_PROVIDER=qwen
DECIDER_MODEL=qwen3.8-max
REFLECTOR_PROVIDER=qwen
REFLECTOR_MODEL=qwen3.8-max
ORCHESTRATOR_PROVIDER=qwen
ORCHESTRATOR_MODEL=qwen3.8-max
```

**Anthropic-compatible endpoint** (routes through `langchain_anthropic.ChatAnthropic`):

```bash
OBSERVER_PROVIDER=qwen-anthropic
OBSERVER_MODEL=qwen3.8-max
DECIDER_PROVIDER=qwen-anthropic
DECIDER_MODEL=qwen3.8-max
REFLECTOR_PROVIDER=qwen-anthropic
REFLECTOR_MODEL=qwen3.8-max
ORCHESTRATOR_PROVIDER=qwen-anthropic
ORCHESTRATOR_MODEL=qwen3.8-max
```

**Requires:** `QWEN_API_KEY` in `.env` (same key for both variants).
Base URLs default to `https://dashscope-intl.aliyuncs.com/compatible-mode/v1`
(OpenAI shape) and `https://dashscope-intl.aliyuncs.com/apps/anthropic`
(Anthropic shape) — override with `QWEN_BASE_URL` / `QWEN_ANTHROPIC_BASE_URL`
if needed.

Note: the Observer's default `OBSERVER_DETECTION_METHOD=llm` requires vision
input + reliable structured/function-calling output (see the note at the top
of this file) — verify grounding works on `qwen3.8-max` before relying on it,
or set `OBSERVER_DETECTION_METHOD=cv_ocr` as a fallback.

---

## BlueSminds AI (https://bluesminds.com)

```bash
OBSERVER_PROVIDER=bluesminds
OBSERVER_MODEL=gpt-5.5
DECIDER_PROVIDER=bluesminds
DECIDER_MODEL=gpt-5.5
REFLECTOR_PROVIDER=bluesminds
REFLECTOR_MODEL=gpt-5.5
ORCHESTRATOR_PROVIDER=bluesminds
ORCHESTRATOR_MODEL=gpt-5.5
```
**Requires:** `BLUESMINDS_API_KEY` in `.env`
**Recommended:** `gpt-5.5` ($10/1M input, $60/1M completion)
**Available models (free tier):** `gpt-4o-mini` only
**Available models (paid):** `gpt-5.5`, `gpt-4o`, `gpt-5-mini`, `gpt-5-nano`, `qwen3.6-27b`, `DeepSeek-V4-Flash`, `MiniMax-M2.7`, `gemini-3.1-pro-preview`, and more (38 total)

---

## OpenRouter

```bash
OBSERVER_PROVIDER=openrouter
OBSERVER_MODEL=google/gemini-2.0-flash-001
DECIDER_PROVIDER=openrouter
DECIDER_MODEL=google/gemini-2.0-flash-001
REFLECTOR_PROVIDER=openrouter
REFLECTOR_MODEL=google/gemini-2.0-flash-001
ORCHESTRATOR_PROVIDER=openrouter
ORCHESTRATOR_MODEL=google/gemini-2.0-flash-001
```
**Requires:** `OPENROUTER_API_KEY` in `.env`

---

## Local (Ollama / LM Studio)

```bash
OBSERVER_PROVIDER=local
OBSERVER_MODEL=llama3.2
DECIDER_PROVIDER=local
DECIDER_MODEL=llama3.2
REFLECTOR_PROVIDER=local
REFLECTOR_MODEL=llama3.2
ORCHESTRATOR_PROVIDER=local
ORCHESTRATOR_MODEL=llama3.2
```
**Requires:** `LOCAL_LLM_URL` pointing to compatible server

---

## OpenAI

```bash
OBSERVER_PROVIDER=openai
OBSERVER_MODEL=gpt-4o
DECIDER_PROVIDER=openai
DECIDER_MODEL=gpt-4o
REFLECTOR_PROVIDER=openai
REFLECTOR_MODEL=gpt-4o-mini
ORCHESTRATOR_PROVIDER=openai
ORCHESTRATOR_MODEL=gpt-4o
```
**Requires:** `OPENAI_API_KEY` in `.env`

---

## LLM7

```bash
OBSERVER_PROVIDER=llm7
OBSERVER_MODEL=gpt-4o
DECIDER_PROVIDER=llm7
DECIDER_MODEL=gpt-4o
REFLECTOR_PROVIDER=llm7
REFLECTOR_MODEL=gpt-4o-mini
ORCHESTRATOR_PROVIDER=llm7
ORCHESTRATOR_MODEL=gpt-4o
```
**Requires:** `LLM7_API_KEY` in `.env`

---

## Cursor

```bash
OBSERVER_PROVIDER=cursor
OBSERVER_MODEL=claude-opus-4.6
DECIDER_PROVIDER=cursor
DECIDER_MODEL=claude-sonnet-4.6
REFLECTOR_PROVIDER=cursor
REFLECTOR_MODEL=claude-sonnet-4.6
ORCHESTRATOR_PROVIDER=cursor
ORCHESTRATOR_MODEL=claude-opus-4.6
```
**Requires:** `CURSOR_API_KEY` in `.env`
