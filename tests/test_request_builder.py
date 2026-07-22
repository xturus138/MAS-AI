import sys
import unittest

sys.path.append(".")
from core.uncertainty.request_builder import (
    ObserverSemanticRequestBuilder,
    HUMAN_TEMPLATE,
    OUTPUT_CONTRACT,
)
from shared.prompts.observer_prompts import SYSTEM_PROMPT, FEW_SHOT_EXAMPLES


def _make():
    return ObserverSemanticRequestBuilder(
        system_prompt=SYSTEM_PROMPT,
        few_shot=FEW_SHOT_EXAMPLES,
        human_template=HUMAN_TEMPLATE,
        output_contract=OUTPUT_CONTRACT,
    )


class TestRequestBuilder(unittest.TestCase):
    def test_build_returns_messages_with_system_and_human(self):
        b = _make()
        msgs = b.build("Notes App", "N/A", '[{"i":1,"t":"Catatan"}]', "ZmFrZQ==")
        self.assertEqual(msgs[0][0], "system")
        # last message is the human turn; its content is a list of parts
        role, content = msgs[-1]
        self.assertEqual(role, "human")
        self.assertIsInstance(content, list)
        kinds = {part["type"] for part in content}
        self.assertIn("text", kinds)
        self.assertIn("image_url", kinds)

    def test_prompt_hash_is_stable_across_dynamic_values(self):
        b = _make()
        h1 = b.prompt_hash
        # building with different dynamic values must not change the hash
        b.build("Different App", "Different Path", "[]", "b3RoZXI=")
        self.assertEqual(b.prompt_hash, h1)

    def test_prompt_hash_changes_when_prompt_changes(self):
        b1 = _make()
        b2 = ObserverSemanticRequestBuilder(
            system_prompt=SYSTEM_PROMPT + " EXTRA",
            few_shot=FEW_SHOT_EXAMPLES,
            human_template=HUMAN_TEMPLATE,
            output_contract=OUTPUT_CONTRACT,
        )
        self.assertNotEqual(b1.prompt_hash, b2.prompt_hash)

    def test_prompt_hash_is_hex_sha256(self):
        b = _make()
        self.assertEqual(len(b.prompt_hash), 64)
        int(b.prompt_hash, 16)  # raises if not hex


if __name__ == "__main__":
    unittest.main()
