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

    def test_convert_to_messages_does_not_crash_on_general_knowledge_placeholder(self):
        """Regression test: SYSTEM_PROMPT contains a {general_knowledge} placeholder.
        convert_to_messages(...) — the exact call both production and DSE call sites
        use — must not raise, and the placeholder must actually be substituted, not
        left literal."""
        from langchain_core.messages import convert_to_messages

        b = _make()
        built = b.build(
            "Notes App", "N/A", '[{"i":1,"t":"Catatan"}]', "ZmFrZQ==",
            general_knowledge="Prior UI fact: buttons are usually bottom-right.",
        )
        msgs = convert_to_messages(built)
        system_content = msgs[0].content
        self.assertNotIn("{general_knowledge}", system_content)
        self.assertIn("Prior UI fact: buttons are usually bottom-right.", system_content)

    def test_convert_to_messages_uses_default_general_knowledge_when_omitted(self):
        from langchain_core.messages import convert_to_messages

        b = _make()
        built = b.build("Notes App", "N/A", '[]', "ZmFrZQ==")
        msgs = convert_to_messages(built)
        self.assertIn("No relevant prior UI knowledge.", msgs[0].content)

    def test_convert_to_messages_does_not_crash_on_json_braces_in_elements(self):
        """Regression test: elements_json (real JSON, contains literal braces) must
        survive convert_to_messages() unmodified. ChatPromptTemplate.from_messages()
        .format_messages() re-templates this and raises KeyError on real screen data —
        convert_to_messages() must not."""
        from langchain_core.messages import convert_to_messages

        b = _make()
        built = b.build(
            "Notes App", "N/A",
            '[{"i": 1, "t": "Catatan"}, {"i": 2, "t": "Semua"}]',
            "ZmFrZQ==",
        )
        msgs = convert_to_messages(built)
        human_content = msgs[-1].content
        text_part = next(p["text"] for p in human_content if p["type"] == "text")
        self.assertIn('{"i": 1, "t": "Catatan"}', text_part)


if __name__ == "__main__":
    unittest.main()
