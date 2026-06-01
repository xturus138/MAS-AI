# MIRIX Memory System Migration Documentation

This document provides a comprehensive technical overview of the migration from a monolithic, state-heavy agent control loop to the **MIRIX (Multi-Agent Memory System) Memory System**. It outlines the before-and-after architecture of the agent state system and contains the complete, production-ready codebase for the entire `memory` module.

---

## 1. Architectural Overview & Shift

### The "Before" Architecture (Monolithic State)
Previously, the `AgentState` class served as a giant monolithic container of both transient execution variables and persistent session data (spanning over 60 fields).
- **Redundancy:** Information such as `task_goal`, `sub_steps`, and Figma target metadata were continuously serialized and passed around the LangGraph network.
- **Cognitive Load:** The LLM agents were forced to ingest a massive payload of irrelevant variables for every single turn, increasing context window usage, latency, and reasoning drift.
- **Staleness & Durability:** There was no concept of long-term memory or semantic memory that survived beyond the active run. If a run terminated or restarted, all learned UI element bounds and procedural knowledge were lost.

### The "After" Architecture (MIRIX Decentralized Memory)
With the migration to the MIRIX Memory System, the `AgentState` was slimmed down to **~30 core fields** focused strictly on the active step's execution loop. All long-term, semantic, episodic, and configuration details were delegated to specialized stores.
- **Gateway Pattern (`MIRIXMemorySystem`):** All agents and system runners communicate exclusively with a single Meta-Manager. Agents do not access the individual memory databases or JSON stores directly.
- **Active Retrieval (`ActiveRetrieval`):** Before making an LLM call, an agent triggers a parallel query across all stores using a ThreadPoolExecutor. It constructs a highly targeted `<memory_context>` block to inject into the LLM system prompt.
- **Parallel Memory Updates:** At the end of an action, the agent reports execution updates to the Meta-Manager in a single `update()` call, which distributes updates in parallel to the appropriate stores.
- **Persistence Boundaries:** 
  - *Session-Specific Stores:* `Core`, `Episodic` (SQLite+FTS5), `Procedural`, and `Resource` memory are written to the current run's output directory.
  - *Cross-Run Persistent Stores:* `Semantic` (SQLite+FTS5 widget annotations) and `KnowledgeVault` (credentials/sensitive tokens) are stored in a persistent directory, allowing agent learning to accumulate and survive across multiple test runs.

---

## 2. Before & After State Comparison

Here is the precise structural difference in `core/models/state.py`:

```python
# ==============================================================================
# BEFORE: Monolithic State (60+ Fields)
# ==============================================================================
from typing import List, Optional, TypedDict

class AgentState(TypedDict):
    tcs_id: str
    navigation_context: str
    scenario_desc: str
    test_type: str
    user_role: str
    sub_steps: List[str]
    task_goal: str
    expected_result: str
    current_sub_step_index: int

    current_step: int
    screenshot_path: str
    previous_screenshot_path: str
    annotated_screenshot_path: str
    ui_elements_summary: str
    ocr_result: str
    detected_elements: str
    observer_analysis: str
    widgets: List[dict]
    
    action_plan: dict
    execution_result: str
    is_completed: bool
    
    action_history: List[dict]
    chat_logs: List[dict]
    orchestrator_reasoning: str
    sender: str
    next_agent: str
    stagnation_count: int          
    previous_ui_summary: str
    reflector_reasoning: str

    output_dir: str
    step_dir: str

    step_retry_count: int
    last_reflector_passed: bool

    figma_enabled: bool
    figma_start_node_id: str
    figma_end_node_id: str
    figma_end_screenshot_b64: str
    figma_bridge_steps: List[str]
    last_agent_calls: List[str]
    session_id: str
    start_time: float
    end_time: float
    recovery_attempts: int

    # Autonomous-mode fields
    orchestrator_instruction: str
    observer_analysis_step: int
    is_final_step: bool

    # Research metrics counters
    steps_completed_count: int
    total_reflector_calls: int
    reflector_pass_count: int
    total_first_verify_calls: int
    reflector_first_pass_count: int
    is_first_verify_attempt: bool
    widget_lookup_success: int
    widget_lookup_fail: int
```

```python
# ==============================================================================
# AFTER: Slimmed AgentState with MIRIX Context (30 Fields)
# ==============================================================================
from typing import List, Optional, TypedDict

class AgentState(TypedDict):
    # ── Control signals ───────────────────────────────────────────────────────
    session_id: str
    tcs_id: str
    sender: str
    next_agent: str
    current_step: int
    is_completed: bool

    # ── Current-step working memory ───────────────────────────────────────────
    screenshot_path: str
    output_dir: str
    step_dir: str
    action_plan: dict
    execution_result: str
    last_reflector_passed: bool

    # ── Current observer output (live, not persisted across steps) ────────────
    observer_analysis: str
    observer_analysis_step: int     # current_step when observer last ran
    widgets: List[dict]

    # ── MIRIX: retrieved memory context injected into every agent prompt ───────
    memory_context: str             # Real-time search results injected into LLM system prompt

    # ── Orchestrator control ──────────────────────────────────────────────────
    current_sub_step_index: int
    orchestrator_instruction: str   # Instruction set by autonomous orchestrator for current step
    is_final_step: bool             # Set by orchestrator when dispatching VERIFY for the final goal
    is_first_verify_attempt: bool   # Set by orchestrator before each reflector dispatch
    step_retry_count: int

    # ── Stagnation / recovery ─────────────────────────────────────────────────
    stagnation_count: int
    recovery_attempts: int
    last_agent_calls: List[str]

    # ── Research metrics counters ─────────────────────────────────────────────
    start_time: float
    end_time: float
    steps_completed_count: int          
    total_reflector_calls: int
    reflector_pass_count: int
    total_first_verify_calls: int
    reflector_first_pass_count: int
    widget_lookup_success: int
    widget_lookup_fail: int
    widget_text_fallback_count: int     # Fallback recoveries via text-match
```

---

## 3. Complete Code Reference: `memory/` Module

Below is the complete, unmodified source code for all components of the MIRIX memory module, formatted and organized exactly as it exists in the filesystem.

```
memory/
├── __init__.py
├── schemas.py
├── meta_manager.py
├── retrieval/
│   ├── __init__.py
│   └── active_retrieval.py
└── stores/
    ├── __init__.py
    ├── core_memory.py
    ├── episodic_memory.py
    ├── semantic_memory.py
    ├── procedural_memory.py
    ├── resource_memory.py
    └── knowledge_vault.py
```

### 3.1 Core Definition and Gateway

#### [schemas.py](file:///c:/Users/radit/Project/VisualStudioProject/Skripsi/MAS%20AI/memory/schemas.py)
```python
from dataclasses import dataclass, field
from typing import List


@dataclass
class CoreEntry:
    key: str
    value: str
    updated_at: str = ""


@dataclass
class EpisodicEntry:
    event_type: str       # "observer_analysis" | "action_executed" | "verification" | "orchestrator_decision"
    summary: str
    details: str
    actor: str            # "observer" | "decider" | "executor" | "reflector" | "orchestrator"
    timestamp: str
    step: int


@dataclass
class SemanticEntry:
    name: str             # widget label / entity identifier
    summary: str          # one-line description
    details: str          # extended context (bounds, screen, function)
    source: str           # "observer" | "inferred"
    screen_context: str   # screen on which this was observed
    bounds: List[int] = field(default_factory=list)  # [x1, y1, x2, y2]


@dataclass
class ProceduralEntry:
    entry_type: str       # "workflow" | "bridge"
    description: str
    steps: List[str]
    tcs_id: str


@dataclass
class ResourceEntry:
    title: str
    summary: str
    resource_type: str    # "screenshot" | "annotated_screenshot" | "figma_gold" | "figma_composite"
    path: str
    step: int
    timestamp: str


@dataclass
class VaultEntry:
    entry_type: str       # "credential" | "api_key" | "device_id"
    key: str
    value: str
    sensitivity: str      # "low" | "medium" | "high"
```

#### [meta_manager.py](file:///c:/Users/radit/Project/VisualStudioProject/Skripsi/MAS%20AI/memory/meta_manager.py)
```python
from concurrent.futures import ThreadPoolExecutor
from memory.stores.core_memory import CoreMemoryStore
from memory.stores.episodic_memory import EpisodicMemoryStore
from memory.stores.semantic_memory import SemanticMemoryStore
from memory.stores.procedural_memory import ProceduralMemoryStore
from memory.stores.resource_memory import ResourceMemoryStore
from memory.stores.knowledge_vault import KnowledgeVaultStore
from memory.retrieval.active_retrieval import ActiveRetrieval


class MIRIXMemorySystem:
    """
    The Meta Memory Manager.

    This is the single gateway all agents call for memory I/O.
    No agent reads from or writes to any store directly.

    Two operations:
      retrieve(topic)  — Active Retrieval: parallel search, tagged context string
      update(packet)   — Memory Update: routes fields to correct stores in parallel
    """

    def __init__(self, session_id: str, output_dir: str, cross_run_dir: str = ""):
        self.session_id = session_id
        self.output_dir = output_dir

        # Session-specific stores (discarded after each run)
        self.core       = CoreMemoryStore(session_id, output_dir)
        self.episodic   = EpisodicMemoryStore(session_id, output_dir)
        self.procedural = ProceduralMemoryStore(session_id, output_dir)
        self.resource   = ResourceMemoryStore(session_id, output_dir)

        # Persistent stores — use cross_run_dir if provided so knowledge survives across runs
        persistent_dir  = cross_run_dir if cross_run_dir else output_dir
        self.semantic   = SemanticMemoryStore(session_id, persistent_dir)
        self.vault      = KnowledgeVaultStore(session_id, persistent_dir)

        self._retriever = ActiveRetrieval(
            self.core, self.episodic, self.semantic,
            self.procedural, self.resource, self.vault,
        )

    # ── Public API ────────────────────────────────────────────────────────────

    def retrieve(self, topic: str, max_per_store: int = 5) -> str:
        """
        Active Retrieval (MIRIX §3.2).
        Searches all stores in parallel and returns a tagged context string.
        Agents inject this string into their LLM system prompt.
        """
        return self._retriever.retrieve(topic, max_per_store)

    def update(self, packet: dict):
        """
        Memory Update Workflow (MIRIX §3.3).
        Routes packet fields to the appropriate Memory Managers in parallel.

        Packet keys (all optional):
          core       — dict  : key/value pairs for CoreMemory
          episodic   — dict  : {event_type, summary, details, actor, step}
          semantic   — list  : [{name, summary, details, source, screen_context, bounds}]
          procedural — dict  : {entry_type, description, steps, tcs_id}
          resource   — dict  : {title, summary, resource_type, path, step}
          vault      — dict  : {entry_type, key, value, sensitivity}
        """
        tasks = []
        if "core" in packet:
            tasks.append(("core",       lambda p=packet["core"]:       self.core.write(p)))
        if "episodic" in packet:
            tasks.append(("episodic",   lambda p=packet["episodic"]:   self.episodic.write(p)))
        if "semantic" in packet:
            tasks.append(("semantic",   lambda p=packet["semantic"]:   self.semantic.write(p)))
        if "procedural" in packet:
            tasks.append(("procedural", lambda p=packet["procedural"]: self.procedural.write(p)))
        if "resource" in packet:
            tasks.append(("resource",   lambda p=packet["resource"]:   self.resource.write(p)))
        if "vault" in packet:
            tasks.append(("vault",      lambda p=packet["vault"]:      self.vault.write(p)))

        if not tasks:
            return

        with ThreadPoolExecutor(max_workers=len(tasks)) as ex:
            futures = {ex.submit(fn): name for name, fn in tasks}
            for future in futures:
                try:
                    future.result(timeout=10)
                except Exception as e:
                    store_name = futures[future]
                    print(f"[MIRIX] Warning: {store_name} update failed: {e}")

    # ── Convenience helpers used by runner at session init ────────────────────

    def init_session(self, scenario: dict, tcs_id: str, figma_context: dict):
        """
        Bootstraps Core Memory and Procedural Memory from scenario data.
        Called once per scenario at the start of runner.
        """
        self.update({
            "core": {
                "tcs_id":             tcs_id,
                "navigation_context": scenario.get("navigation_context", ""),
                "scenario_desc":      scenario.get("scenario_desc", ""),
                "test_type":          scenario.get("test_type", ""),
                "user_role":          scenario.get("user_role", ""),
                "task_goal":          scenario.get("task_goal", scenario.get("scenario_desc", "")),
                "expected_result":    scenario.get("expected_result", ""),
                "figma_enabled":      str(figma_context.get("figma_enabled", False)),
                "figma_end_node_id":  figma_context.get("figma_end_node_id", ""),
                "figma_start_node_id": figma_context.get("figma_start_node_id", ""),
            }
        })
        sub_steps = scenario.get("sub_steps", [])
        if sub_steps:
            self.update({
                "procedural": {
                    "entry_type":  "workflow",
                    "description": scenario.get("scenario_desc", ""),
                    "steps":       sub_steps,
                    "tcs_id":      tcs_id,
                }
            })

        # Persist Figma Gold Standard image to disk → Resource Memory
        figma_b64 = figma_context.get("figma_end_screenshot_b64", "")
        if figma_b64:
            self.resource.save_figma_gold(figma_b64, self.output_dir)

    def close(self):
        """Call at the end of a scenario to cleanly close SQLite connections."""
        self.episodic.close()
        self.semantic.close()
```

---

### 3.2 Active Retrieval Layer

#### [active_retrieval.py](file:///c:/Users/radit/Project/VisualStudioProject/Skripsi/MAS%20AI/memory/retrieval/active_retrieval.py)
```python
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from memory.stores import (
        CoreMemoryStore, EpisodicMemoryStore, SemanticMemoryStore,
        ProceduralMemoryStore, ResourceMemoryStore, KnowledgeVaultStore,
    )


def _format_core(entries) -> str:
    if not entries:
        return ""
    lines = [f"  {e.key}: {e.value}" for e in entries]
    return "<core_memory>\n" + "\n".join(lines) + "\n</core_memory>"


def _format_episodic(entries) -> str:
    if not entries:
        return ""
    lines = []
    for e in entries:
        lines.append(f"  [{e.timestamp}] [{e.actor}] step={e.step} | {e.event_type}: {e.summary}")
        if e.details:
            lines.append(f"    {e.details[:300]}")
    return "<episodic_memory>\n" + "\n".join(lines) + "\n</episodic_memory>"


def _format_semantic(entries) -> str:
    if not entries:
        return ""
    lines = []
    for e in entries:
        bounds_str = f" bounds={e.bounds}" if e.bounds else ""
        lines.append(f"  [{e.name}]{bounds_str}: {e.summary}")
        if e.details:
            lines.append(f"    {e.details[:200]}")
    return "<semantic_memory>\n" + "\n".join(lines) + "\n</semantic_memory>"


def _format_procedural(entries) -> str:
    if not entries:
        return ""
    lines = []
    for e in entries:
        lines.append(f"  [{e.entry_type}] {e.description} (tcs={e.tcs_id})")
        for i, step in enumerate(e.steps, 1):
            lines.append(f"    {i}. {step}")
    return "<procedural_memory>\n" + "\n".join(lines) + "\n</procedural_memory>"


def _format_resource(entries) -> str:
    if not entries:
        return ""
    lines = []
    for e in entries:
        lines.append(f"  [{e.resource_type}] step={e.step} path={e.path} | {e.summary}")
    return "<resource_memory>\n" + "\n".join(lines) + "\n</resource_memory>"


class ActiveRetrieval:
    """
    Implements MIRIX Active Retrieval (Section 3.2 of the paper).

    Given a topic string, it searches all six memory stores in parallel
    and returns a tagged context string ready for injection into an LLM prompt.
    """

    def __init__(
        self,
        core: "CoreMemoryStore",
        episodic: "EpisodicMemoryStore",
        semantic: "SemanticMemoryStore",
        procedural: "ProceduralMemoryStore",
        resource: "ResourceMemoryStore",
        vault: "KnowledgeVaultStore",
    ):
        self._core = core
        self._episodic = episodic
        self._semantic = semantic
        self._procedural = procedural
        self._resource = resource
        self._vault = vault

    def retrieve(self, topic: str, max_per_store: int = 5) -> str:
        """
        Active Retrieval: search all stores in parallel, tag results by source.
        Returns a multi-tag context string ready for LLM injection.
        """
        tasks = {
            "core":       lambda: self._core.search(topic),
            "episodic":   lambda: self._episodic.search(topic, max_per_store),
            "semantic":   lambda: self._semantic.search(topic, max_per_store),
            "procedural": lambda: self._procedural.search(topic),
            "resource":   lambda: self._resource.search(topic, max_per_store),
        }

        results = {}
        with ThreadPoolExecutor(max_workers=5) as ex:
            futures = {ex.submit(fn): name for name, fn in tasks.items()}
            for future in as_completed(futures):
                name = futures[future]
                try:
                    results[name] = future.result(timeout=5)
                except Exception:
                    results[name] = []

        parts = []
        core_str = _format_core(results.get("core", []))
        epis_str = _format_episodic(results.get("episodic", []))
        sem_str  = _format_semantic(results.get("semantic", []))
        proc_str = _format_procedural(results.get("procedural", []))
        res_str  = _format_resource(results.get("resource", []))

        for s in (core_str, epis_str, sem_str, proc_str, res_str):
            if s:
                parts.append(s)

        return "\n\n".join(parts)
```

---

### 3.3 Storage Layer (Specialized Stores)

#### [core_memory.py](file:///c:/Users/radit/Project/VisualStudioProject/Skripsi/MAS%20AI/memory/stores/core_memory.py)
```python
import json
import os
import datetime
from typing import List
from memory.schemas import CoreEntry


class CoreMemoryStore:
    """
    Stores high-priority, persistent session constants that are always
    available to every agent. Backed by a single JSON file per session.
    """

    def __init__(self, session_id: str, output_dir: str):
        self._path = os.path.join(output_dir, "memory", "core.json")
        os.makedirs(os.path.dirname(self._path), exist_ok=True)
        self._data: dict[str, str] = {}
        if os.path.exists(self._path):
            with open(self._path, "r", encoding="utf-8") as f:
                self._data = json.load(f)

    def write(self, entries: dict):
        """Bulk-set key/value pairs. Each call merges into existing data."""
        now = datetime.datetime.now().isoformat(timespec="seconds")
        for k, v in entries.items():
            self._data[k] = str(v)
        self._flush()

    def get(self, key: str, default: str = "") -> str:
        return self._data.get(key, default)

    def search(self, topic: str) -> List[CoreEntry]:
        topic_lower = topic.lower()
        results = []
        for k, v in self._data.items():
            if topic_lower in k.lower() or topic_lower in v.lower():
                results.append(CoreEntry(key=k, value=v))
        # Always include the core constants most useful for agents
        priority_keys = [
            "tcs_id", "task_goal", "expected_result", "scenario_desc",
            "user_role", "navigation_context", "test_type",
            "figma_enabled", "figma_end_node_id",
        ]
        for pk in priority_keys:
            if pk in self._data and not any(r.key == pk for r in results):
                results.append(CoreEntry(key=pk, value=self._data[pk]))
        return results

    def all(self) -> dict:
        return dict(self._data)

    def _flush(self):
        with open(self._path, "w", encoding="utf-8") as f:
            json.dump(self._data, f, indent=2, ensure_ascii=False)
```

#### [episodic_memory.py](file:///c:/Users/radit/Project/VisualStudioProject/Skripsi/MAS%20AI/memory/stores/episodic_memory.py)
```python
import sqlite3
import datetime
import os
from typing import List
from memory.schemas import EpisodicEntry


class EpisodicMemoryStore:
    """
    Stores time-stamped events in order — the agent's living activity log.
    Backed by SQLite with FTS5 for keyword search.
    """

    def __init__(self, session_id: str, output_dir: str):
        db_dir = os.path.join(output_dir, "memory")
        os.makedirs(db_dir, exist_ok=True)
        self._db_path = os.path.join(db_dir, "episodic.db")
        self._conn = sqlite3.connect(self._db_path, check_same_thread=False)
        self._create_tables()

    def _create_tables(self):
        self._conn.execute("""
            CREATE TABLE IF NOT EXISTS episodes (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                event_type  TEXT NOT NULL,
                summary     TEXT NOT NULL,
                details     TEXT,
                actor       TEXT,
                timestamp   TEXT,
                step        INTEGER DEFAULT 0
            )
        """)
        self._conn.execute("""
            CREATE VIRTUAL TABLE IF NOT EXISTS episodes_fts
            USING fts5(summary, details, content='episodes', content_rowid='id')
        """)
        self._conn.execute("""
            CREATE TRIGGER IF NOT EXISTS episodes_ai AFTER INSERT ON episodes BEGIN
                INSERT INTO episodes_fts(rowid, summary, details)
                VALUES (new.id, new.summary, new.details);
            END
        """)
        self._conn.commit()

    def write(self, entry: dict):
        """
        entry keys: event_type, summary, details, actor, step
        """
        now = datetime.datetime.now().isoformat(timespec="seconds")
        self._conn.execute(
            "INSERT INTO episodes (event_type, summary, details, actor, timestamp, step) "
            "VALUES (?,?,?,?,?,?)",
            (
                entry.get("event_type", "unknown"),
                entry.get("summary", ""),
                entry.get("details", ""),
                entry.get("actor", "system"),
                entry.get("timestamp", now),
                entry.get("step", 0),
            ),
        )
        self._conn.commit()

    def search(self, topic: str, max_results: int = 5) -> List[EpisodicEntry]:
        results = []
        try:
            # FTS keyword search first
            cur = self._conn.execute(
                "SELECT e.event_type, e.summary, e.details, e.actor, e.timestamp, e.step "
                "FROM episodes e "
                "JOIN episodes_fts f ON e.id = f.rowid "
                "WHERE episodes_fts MATCH ? "
                "ORDER BY e.id DESC LIMIT ?",
                (self._fts_query(topic), max_results),
            )
            for row in cur.fetchall():
                results.append(EpisodicEntry(*row))
        except Exception:
            pass

        # Always append the last N episodes regardless of topic
        needed = max_results - len(results)
        if needed > 0:
            cur = self._conn.execute(
                "SELECT event_type, summary, details, actor, timestamp, step "
                "FROM episodes ORDER BY id DESC LIMIT ?",
                (needed,),
            )
            seen = {(r.actor, r.step, r.event_type) for r in results}
            for row in cur.fetchall():
                entry = EpisodicEntry(*row)
                key = (entry.actor, entry.step, entry.event_type)
                if key not in seen:
                    results.append(entry)
                    seen.add(key)

        return results

    def last(self, n: int = 5) -> List[EpisodicEntry]:
        cur = self._conn.execute(
            "SELECT event_type, summary, details, actor, timestamp, step "
            "FROM episodes ORDER BY id DESC LIMIT ?",
            (n,),
        )
        return [EpisodicEntry(*row) for row in cur.fetchall()]

    def last_by_actor(self, actor: str) -> EpisodicEntry | None:
        cur = self._conn.execute(
            "SELECT event_type, summary, details, actor, timestamp, step "
            "FROM episodes WHERE actor=? ORDER BY id DESC LIMIT 1",
            (actor,),
        )
        row = cur.fetchone()
        return EpisodicEntry(*row) if row else None

    def all_as_dicts(self) -> list:
        cur = self._conn.execute(
            "SELECT event_type, summary, details, actor, timestamp, step FROM episodes ORDER BY id"
        )
        cols = ["event_type", "summary", "details", "actor", "timestamp", "step"]
        return [dict(zip(cols, row)) for row in cur.fetchall()]

    def close(self):
        self._conn.close()

    @staticmethod
    def _fts_query(topic: str) -> str:
        # Escape special FTS5 characters and build OR query from words
        words = [w.strip('"') for w in topic.split() if len(w) > 2]
        if not words:
            return '""'
        return " OR ".join(f'"{w}"' for w in words[:8])
```

#### [semantic_memory.py](file:///c:/Users/radit/Project/VisualStudioProject/Skripsi/MAS%20AI/memory/stores/semantic_memory.py)
```python
import sqlite3
import datetime
import os
from typing import List
from memory.schemas import SemanticEntry


class SemanticMemoryStore:
    """
    Accumulates abstract, time-independent knowledge about UI elements and
    the application — the agent's evolving understanding of the app under test.
    Backed by SQLite with FTS5 for keyword search.
    """

    def __init__(self, session_id: str, output_dir: str):
        db_dir = os.path.join(output_dir, "memory")
        os.makedirs(db_dir, exist_ok=True)
        self._db_path = os.path.join(db_dir, "semantic.db")
        self._conn = sqlite3.connect(self._db_path, check_same_thread=False)
        self._create_tables()

    def _create_tables(self):
        self._conn.execute("""
            CREATE TABLE IF NOT EXISTS knowledge (
                id             INTEGER PRIMARY KEY AUTOINCREMENT,
                name           TEXT NOT NULL,
                summary        TEXT,
                details        TEXT,
                source         TEXT DEFAULT 'observer',
                screen_context TEXT,
                bounds_json    TEXT DEFAULT '[]',
                updated_at     TEXT
            )
        """)
        self._conn.execute("""
            CREATE VIRTUAL TABLE IF NOT EXISTS knowledge_fts
            USING fts5(name, summary, details, content='knowledge', content_rowid='id')
        """)
        self._conn.execute("""
            CREATE TRIGGER IF NOT EXISTS knowledge_ai AFTER INSERT ON knowledge BEGIN
                INSERT INTO knowledge_fts(rowid, name, summary, details)
                VALUES (new.id, new.name, new.summary, new.details);
            END
        """)
        self._conn.execute("""
            CREATE TRIGGER IF NOT EXISTS knowledge_au AFTER UPDATE ON knowledge BEGIN
                INSERT INTO knowledge_fts(knowledge_fts, rowid, name, summary, details)
                VALUES ('delete', old.id, old.name, old.summary, old.details);
                INSERT INTO knowledge_fts(rowid, name, summary, details)
                VALUES (new.id, new.name, new.summary, new.details);
            END
        """)
        self._conn.commit()

    def write(self, entries: list):
        """
        entries: list of dicts with keys: name, summary, details, source, screen_context, bounds
        Upserts by name — same widget updated if already known.
        """
        import json
        now = datetime.datetime.now().isoformat(timespec="seconds")
        for e in entries:
            name = e.get("name", "").strip()
            if not name:
                continue
            existing = self._conn.execute(
                "SELECT id FROM knowledge WHERE name=?", (name,)
            ).fetchone()
            if existing:
                self._conn.execute(
                    "UPDATE knowledge SET summary=?, details=?, source=?, "
                    "screen_context=?, bounds_json=?, updated_at=? WHERE id=?",
                    (
                        e.get("summary", ""),
                        e.get("details", ""),
                        e.get("source", "observer"),
                        e.get("screen_context", ""),
                        json.dumps(e.get("bounds", [])),
                        now,
                        existing[0],
                    ),
                )
            else:
                self._conn.execute(
                    "INSERT INTO knowledge (name, summary, details, source, screen_context, bounds_json, updated_at) "
                    "VALUES (?,?,?,?,?,?,?)",
                    (
                        name,
                        e.get("summary", ""),
                        e.get("details", ""),
                        e.get("source", "observer"),
                        e.get("screen_context", ""),
                        json.dumps(e.get("bounds", [])),
                        now,
                    ),
                )
        self._conn.commit()

    def search(self, topic: str, max_results: int = 8) -> List[SemanticEntry]:
        import json
        results = []
        try:
            cur = self._conn.execute(
                "SELECT k.name, k.summary, k.details, k.source, k.screen_context, k.bounds_json "
                "FROM knowledge k "
                "JOIN knowledge_fts f ON k.id = f.rowid "
                "WHERE knowledge_fts MATCH ? "
                "ORDER BY k.updated_at DESC LIMIT ?",
                (self._fts_query(topic), max_results),
            )
            for row in cur.fetchall():
                results.append(SemanticEntry(
                    name=row[0], summary=row[1], details=row[2],
                    source=row[3], screen_context=row[4],
                    bounds=json.loads(row[5] or "[]"),
                ))
        except Exception:
            pass

        # Fallback: return most-recently-updated entries if FTS finds nothing
        if not results:
            cur = self._conn.execute(
                "SELECT name, summary, details, source, screen_context, bounds_json "
                "FROM knowledge ORDER BY updated_at DESC LIMIT ?",
                (max_results,),
            )
            for row in cur.fetchall():
                results.append(SemanticEntry(
                    name=row[0], summary=row[1], details=row[2],
                    source=row[3], screen_context=row[4],
                    bounds=json.loads(row[5] or "[]"),
                ))
        return results

    def close(self):
        self._conn.close()

    @staticmethod
    def _fts_query(topic: str) -> str:
        words = [w.strip('"') for w in topic.split() if len(w) > 2]
        if not words:
            return '""'
        return " OR ".join(f'"{w}"' for w in words[:8])
```

#### [procedural_memory.py](file:///c:/Users/radit/Project/VisualStudioProject/Skripsi/MAS%20AI/memory/stores/procedural_memory.py)
```python
import json
import os
from typing import List
from memory.schemas import ProceduralEntry


class ProceduralMemoryStore:
    """
    Stores structured, goal-directed processes: test case sub-steps and
    bridge navigation sequences. Backed by a JSON file per session.
    """

    def __init__(self, session_id: str, output_dir: str):
        self._path = os.path.join(output_dir, "memory", "procedural.json")
        os.makedirs(os.path.dirname(self._path), exist_ok=True)
        self._entries: List[dict] = []
        if os.path.exists(self._path):
            with open(self._path, "r", encoding="utf-8") as f:
                self._entries = json.load(f)

    def write(self, entry: dict):
        """
        entry keys: entry_type, description, steps (list[str]), tcs_id
        Replaces existing entry with same tcs_id + entry_type if present.
        """
        tcs_id = entry.get("tcs_id", "")
        entry_type = entry.get("entry_type", "workflow")
        existing_idx = next(
            (i for i, e in enumerate(self._entries)
             if e.get("tcs_id") == tcs_id and e.get("entry_type") == entry_type),
            None,
        )
        if existing_idx is not None:
            self._entries[existing_idx] = entry
        else:
            self._entries.append(entry)
        self._flush()

    def get_steps(self, tcs_id: str, entry_type: str = "workflow") -> List[str]:
        for e in self._entries:
            if e.get("tcs_id") == tcs_id and e.get("entry_type") == entry_type:
                return e.get("steps", [])
        return []

    def search(self, topic: str) -> List[ProceduralEntry]:
        topic_lower = topic.lower()
        results = []
        for e in self._entries:
            if (topic_lower in e.get("description", "").lower()
                    or topic_lower in e.get("tcs_id", "").lower()
                    or any(topic_lower in s.lower() for s in e.get("steps", []))):
                results.append(ProceduralEntry(
                    entry_type=e.get("entry_type", "workflow"),
                    description=e.get("description", ""),
                    steps=e.get("steps", []),
                    tcs_id=e.get("tcs_id", ""),
                ))
        # Always return the full entry list if search returns nothing
        if not results:
            results = [
                ProceduralEntry(
                    entry_type=e.get("entry_type", "workflow"),
                    description=e.get("description", ""),
                    steps=e.get("steps", []),
                    tcs_id=e.get("tcs_id", ""),
                )
                for e in self._entries
            ]
        return results

    def _flush(self):
        with open(self._path, "w", encoding="utf-8") as f:
            json.dump(self._entries, f, indent=2, ensure_ascii=False)
```

#### [resource_memory.py](file:///c:/Users/radit/Project/VisualStudioProject/Skripsi/MAS%20AI/memory/stores/resource_memory.py)
```python
import json
import os
import base64
import datetime
from typing import List, Optional
from memory.schemas import ResourceEntry


class ResourceMemoryStore:
    """
    Manages file references for screenshots, Figma gold standards, and other
    media. The actual binary data stays on disk; this store tracks metadata.
    """

    def __init__(self, session_id: str, output_dir: str):
        self._path = os.path.join(output_dir, "memory", "resource.json")
        os.makedirs(os.path.dirname(self._path), exist_ok=True)
        self._entries: List[dict] = []
        if os.path.exists(self._path):
            with open(self._path, "r", encoding="utf-8") as f:
                self._entries = json.load(f)

    def write(self, entry: dict):
        """
        entry keys: title, summary, resource_type, path, step
        """
        self._entries.append({
            "title":         entry.get("title", ""),
            "summary":       entry.get("summary", ""),
            "resource_type": entry.get("resource_type", "screenshot"),
            "path":          entry.get("path", ""),
            "step":          entry.get("step", 0),
            "timestamp":     entry.get("timestamp", datetime.datetime.now().isoformat(timespec="seconds")),
        })
        self._flush()

    def save_figma_gold(self, b64_data: str, output_dir: str) -> str:
        """
        Decodes a base64 Figma screenshot, saves it to disk, and registers
        the path in Resource Memory. Returns the saved file path.
        """
        if not b64_data:
            return ""
        dest = os.path.join(output_dir, "memory", "figma_end.png")
        try:
            with open(dest, "wb") as f:
                f.write(base64.b64decode(b64_data))
            self.write({
                "title":         "figma_gold_standard",
                "summary":       "Figma end-state Gold Standard for final verification",
                "resource_type": "figma_gold",
                "path":          dest,
                "step":          0,
            })
        except Exception:
            return ""
        return dest

    def get_figma_gold_b64(self) -> str:
        """Reads the Figma gold standard from disk and returns as base64."""
        entry = self._find_by_type("figma_gold")
        if not entry:
            return ""
        path = entry.get("path", "")
        if not path or not os.path.exists(path):
            return ""
        try:
            with open(path, "rb") as f:
                return base64.b64encode(f.read()).decode("utf-8")
        except Exception:
            return ""

    def get_latest_screenshot_path(self, resource_type: str = "screenshot") -> str:
        for entry in reversed(self._entries):
            if entry.get("resource_type") == resource_type:
                return entry.get("path", "")
        return ""

    def search(self, topic: str, max_results: int = 3) -> List[ResourceEntry]:
        topic_lower = topic.lower()
        results = []
        for e in reversed(self._entries):
            if (topic_lower in e.get("title", "").lower()
                    or topic_lower in e.get("summary", "").lower()
                    or topic_lower in e.get("resource_type", "").lower()):
                results.append(self._to_entry(e))
            if len(results) >= max_results:
                break
        # Always include the most recent screenshot and figma gold if present
        for rtype in ("figma_gold", "screenshot"):
            path = self.get_latest_screenshot_path(rtype)
            if path and not any(r.path == path for r in results):
                e = self._find_by_path(path)
                if e:
                    results.append(self._to_entry(e))
        return results[:max_results + 2]

    def _find_by_type(self, resource_type: str) -> Optional[dict]:
        for e in reversed(self._entries):
            if e.get("resource_type") == resource_type:
                return e
        return None

    def _find_by_path(self, path: str) -> Optional[dict]:
        for e in reversed(self._entries):
            if e.get("path") == path:
                return e
        return None

    @staticmethod
    def _to_entry(e: dict) -> ResourceEntry:
        return ResourceEntry(
            title=e.get("title", ""),
            summary=e.get("summary", ""),
            resource_type=e.get("resource_type", ""),
            path=e.get("path", ""),
            step=e.get("step", 0),
            timestamp=e.get("timestamp", ""),
        )

    def _flush(self):
        with open(self._path, "w", encoding="utf-8") as f:
            json.dump(self._entries, f, indent=2, ensure_ascii=False)
```

#### [knowledge_vault.py](file:///c:/Users/radit/Project/VisualStudioProject/Skripsi/MAS%20AI/memory/stores/knowledge_vault.py)
```python
import json
import os
from typing import List, Optional
from memory.schemas import VaultEntry


class KnowledgeVaultStore:
    """
    Secure repository for verbatim and sensitive data: test credentials,
    API keys, device IDs. High-sensitivity entries are excluded from
    general retrieval and only surfaced via explicit key lookup.
    """

    def __init__(self, session_id: str, output_dir: str):
        self._path = os.path.join(output_dir, "memory", "vault.json")
        os.makedirs(os.path.dirname(self._path), exist_ok=True)
        self._entries: List[dict] = []
        if os.path.exists(self._path):
            with open(self._path, "r", encoding="utf-8") as f:
                self._entries = json.load(f)

    def write(self, entry: dict):
        """
        entry keys: entry_type, key, value, sensitivity
        """
        existing_idx = next(
            (i for i, e in enumerate(self._entries) if e.get("key") == entry.get("key")),
            None,
        )
        if existing_idx is not None:
            self._entries[existing_idx] = entry
        else:
            self._entries.append(entry)
        self._flush()

    def get(self, key: str) -> Optional[str]:
        for e in self._entries:
            if e.get("key") == key:
                return e.get("value", "")
        return None

    def search(self, topic: str) -> List[VaultEntry]:
        """
        Only surfaces low/medium sensitivity entries in search.
        High-sensitivity items require explicit key lookup via get().
        """
        topic_lower = topic.lower()
        results = []
        for e in self._entries:
            if e.get("sensitivity", "high") == "high":
                continue
            if (topic_lower in e.get("key", "").lower()
                    or topic_lower in e.get("entry_type", "").lower()):
                results.append(VaultEntry(
                    entry_type=e.get("entry_type", ""),
                    key=e.get("key", ""),
                    value="[REDACTED]",
                    sensitivity=e.get("sensitivity", "low"),
                ))
        return results

    def _flush(self):
        with open(self._path, "w", encoding="utf-8") as f:
            json.dump(self._entries, f, indent=2, ensure_ascii=False)
```
