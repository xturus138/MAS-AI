# MAS AI — Multi-Agent Android Testing Framework

A multi-agent system (MAS) for automated Android GUI testing, built with LangGraph. Agents collaborate to observe, decide, execute, verify, and record test actions on a real Android device.

---

## Primary Branch

This is the **main development timeline** of the MAS AI project. It is currently being evolved to host a fully integrated multi-agent system that combines:

1.  **Autonomous Goal-Seeking**: The agent can navigate and interact with the app purely based on high-level goals.
2.  **Design-Verified Scenarios**: Full integration with **Figma Prototypes** to ensure the app matches the intended design ("Gold Standard").
3.  **Comprehensive Toolset**: Built-in ADB adapters, OCR/CV perception, and session recording.

---

## Project Status

- **Figma Integration**: [In Progress] Migrating from `multiagent-workflow` branch.
- **Modular Architecture**: [Experimental] See `feature/modular-workflow` for comparison testing.

---

## Quick Start

1. Copy `.env.example` to `.env` and fill in your keys.
2. Connect your Android device via ADB.
3. Run:
   ```bash
   python main.py
   ```
