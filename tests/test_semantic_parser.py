import sys
import unittest

sys.path.append(".")
from core.uncertainty.semantic_parser import parse_semantic_map


class TestSemanticParser(unittest.TestCase):
    SAMPLE = (
        "SEMANTIC_MAP:\n"
        "[1]: Header Text - Catatan\n"
        "[2]: Tab/Filter Button - Semua\n"
        "[3]: Floating Action Button (FAB) - + (Add new note)\n"
        "SUMMARY: The screen displays a notes dashboard."
    )

    def test_basic_parse(self):
        result = parse_semantic_map(self.SAMPLE)
        self.assertEqual(result[1], "Header Text - Catatan")
        self.assertEqual(result[2], "Tab/Filter Button - Semua")
        self.assertEqual(result[3], "Floating Action Button (FAB) - + (Add new note)")
        self.assertNotIn("SUMMARY", " ".join(str(k) for k in result))

    def test_double_bracket_ids(self):
        result = parse_semantic_map("[[10]]: Input Field - Email")
        self.assertEqual(result[10], "Input Field - Email")

    def test_id_range_expands(self):
        result = parse_semantic_map("[2-5]: On-Screen Keyboard (grouped as single block)")
        for i in (2, 3, 4, 5):
            self.assertEqual(result[i], "On-Screen Keyboard (grouped as single block)")

    def test_empty_and_malformed(self):
        self.assertEqual(parse_semantic_map(""), {})
        self.assertEqual(parse_semantic_map(None), {})
        self.assertEqual(parse_semantic_map("no ids here at all"), {})
        # a malformed line is skipped, valid lines still parse
        result = parse_semantic_map("garbage line\n[7]: Button - OK")
        self.assertEqual(result, {7: "Button - OK"})


if __name__ == "__main__":
    unittest.main()
