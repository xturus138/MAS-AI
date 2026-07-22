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
    The Meta Memory Manager (MIRIX).

    Single gateway for all agent memory I/O. No agent reads from or writes
    to any store directly. Implements 6 memory stores based on the CoALA
    framework plus MIRIX extensions:

    Long-Term Memories:
      - Episodic   (SQLite+FTS5): Timestamped event log for self-evaluation
      - Semantic   (SQLite+FTS5): UI concepts/widget descriptions for cross-step recall
      - Procedural (JSON):        Ordered sub-steps from scenario.xlsx
      - Core       (JSON):        Immutable session facts (task_goal, expected_result)
      - Resource   (JSON+disk):   Binary assets (Figma gold standard, screenshots)
      - Vault      (JSON):        Domain heuristics accumulated across runs

    Short-Term (not stored here):
      - Working Memory: AgentState TypedDict, ephemeral per-step

    Two operations:
      retrieve(topic)  — Active Retrieval: parallel search, tagged context string
      update(packet)   — Memory Update: routes fields to correct stores in parallel
    """

    def __init__(self, session_id: str, output_dir: str, cross_run_dir: str = ""):
        self.session_id = session_id
        self.output_dir = output_dir

        self.core       = CoreMemoryStore(session_id, output_dir)
        self.episodic   = EpisodicMemoryStore(session_id, output_dir)
        self.procedural = ProceduralMemoryStore(session_id, output_dir)
        self.resource   = ResourceMemoryStore(session_id, output_dir)

        persistent_dir  = cross_run_dir if cross_run_dir else output_dir
        self.semantic   = SemanticMemoryStore(session_id, persistent_dir)
        self.vault      = KnowledgeVaultStore(session_id, persistent_dir)

        self._retriever = ActiveRetrieval(
            self.core, self.episodic, self.semantic,
            self.procedural, self.resource, self.vault,
        )


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

        figma_b64 = figma_context.get("figma_end_screenshot_b64", "")
        if figma_b64:
            self.resource.save_figma_gold(figma_b64, self.output_dir)

    def close(self):
        """Call at the end of a scenario to cleanly close SQLite connections."""
        self.episodic.close()
        self.semantic.close()
