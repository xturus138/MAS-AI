"""Dynamic scenario.xlsx loading for the Test Suites Management screen.

Workbook-agnostic: works against any scenario.xlsx path, any case count,
any module set. Never assumes scenarios/firebase_chat/ or a fixed 69 cases.
"""

from __future__ import annotations

from dataclasses import dataclass

from core.utils.xlsx_loader import load_scenarios

UNTESTED = "untested"


@dataclass(frozen=True)
class WorkbookCase:
    tcs_id: str
    module: str
    scenario_title: str
    steps: int
    precondition: str
    status: str


def load_workbook_cases(xlsx_path: str, manifest: dict | None) -> list[WorkbookCase]:
    """Load every case in *xlsx_path* and join its last known status.

    *manifest* is a batch_manifest.json payload (see
    core/workflow/predefined/batch.py) from the most recent run against this
    workbook, or None if no run has happened yet. Every case not found in
    the manifest (or when manifest is None) is reported as "untested".
    """
    status_by_tcs_id: dict[str, str] = {}
    if manifest:
        for case in manifest.get("cases", []):
            status_by_tcs_id[str(case["tcs_id"])] = str(case["status"])

    raw_scenarios = load_scenarios(xlsx_path)
    cases: list[WorkbookCase] = []
    for scenario in raw_scenarios:
        tcs_id = str(scenario["tcs_id"])
        cases.append(
            WorkbookCase(
                tcs_id=tcs_id,
                module=str(scenario.get("navigation_context") or "-").split(" > ")[0],
                scenario_title=str(scenario.get("scenario_desc") or ""),
                steps=len(scenario.get("sub_steps") or []),
                precondition=str(scenario.get("navigation_context") or "-"),
                status=status_by_tcs_id.get(tcs_id, UNTESTED),
            )
        )
    return cases
