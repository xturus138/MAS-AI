"""Builds the Observer semantic-interpretation messages and a runtime prompt hash.

This is the single source of truth for Observer message construction. Both the
production ObserverAgent and the standalone uncertainty runner build messages
through this class, so any future prompt/format change reaches both paths.
"""
import hashlib
import json

# Human-turn instruction text (kept identical to the production Observer call).
HUMAN_TEXT = (
    "App Context: {scenario_desc}\n"
    "Navigation Path: {navigation_context}\n"
    "Elements: {elements_json}\n\n"
    "Each element has id (i), text (t), and optional role (r) from XML metadata "
    "(e.g. icon_button, button, input, text). Use role to correctly classify "
    "interactive elements — an element with role=icon_button IS a clickable "
    "icon/button, not placeholder text.\n\n"
    "Map every ID in the screenshot to its generic UI function. Be objective. "
    "Do not reference any task or goal."
)
# Alias used by callers/tests as the "human template" hash input.
HUMAN_TEMPLATE = HUMAN_TEXT

# The output contract the Observer prompt promises (SEMANTIC_MAP shape).
OUTPUT_CONTRACT = (
    "SEMANTIC_MAP:\n[[ID]]: [UI Element Type] - [Visible Text or Icon Description]\n"
    "...\nSUMMARY: [one sentence]"
)


class ObserverSemanticRequestBuilder:
    def __init__(self, system_prompt, few_shot, human_template, output_contract):
        self._system_prompt = system_prompt
        self._few_shot = few_shot
        self._human_template = human_template
        self._output_contract = output_contract
        self._prompt_hash = self._compute_hash()

    def _compute_hash(self) -> str:
        payload = "\x1f".join(
            [
                self._system_prompt or "",
                json.dumps(self._few_shot, ensure_ascii=False, sort_keys=True),
                self._human_template or "",
                self._output_contract or "",
            ]
        )
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()

    @property
    def prompt_hash(self) -> str:
        return self._prompt_hash

    def build(self, scenario_desc, navigation_context, elements_json, img_b64) -> list:
        messages = [("system", self._system_prompt)]
        for role, content in self._few_shot:
            messages.append((role, content))
        human_text = self._human_template.format(
            scenario_desc=scenario_desc,
            navigation_context=navigation_context,
            elements_json=elements_json,
        )
        messages.append(
            (
                "human",
                [
                    {"type": "text", "text": human_text},
                    {
                        "type": "image_url",
                        "image_url": {"url": f"data:image/webp;base64,{img_b64}"},
                    },
                ],
            )
        )
        return messages
