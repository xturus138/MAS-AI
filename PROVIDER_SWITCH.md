# MAS AI — Provider Quick-Switch Guide

Copy-paste the block you want into `.env` to swap all 4 agents at once.

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