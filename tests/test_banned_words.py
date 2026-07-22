# tests/test_banned_words.py
import sys
import unittest

sys.path.append(".")
from core.uncertainty.banned_words import BANNED_WORDS, contains_banned_word


class TestBannedWords(unittest.TestCase):
    def test_detects_each_banned_word(self):
        for word in BANNED_WORDS:
            self.assertTrue(
                contains_banned_word(f"This widget was {word} in the samples."),
                f"expected to detect banned word: {word}",
            )

    def test_case_insensitive(self):
        self.assertTrue(contains_banned_word("The result was UNCERTAIN."))
        self.assertTrue(contains_banned_word("The result was Failed."))

    def test_word_boundary_no_false_positive_on_substring(self):
        # "pass" must not match inside "passed" or "passenger"; "bad" must not
        # match inside "badge"; "good" must not match inside "goods".
        self.assertFalse(contains_banned_word("The value passed through the field."))
        self.assertFalse(contains_banned_word("A passenger icon was shown."))
        self.assertFalse(contains_banned_word("A badge icon was shown."))
        self.assertFalse(contains_banned_word("Goods were listed on the shelf."))

    def test_clean_text_returns_false(self):
        clean = (
            "3 of 5 interpretations described it as a share icon, "
            "2 described it as a text divider."
        )
        self.assertFalse(contains_banned_word(clean))

    def test_empty_string_returns_false(self):
        self.assertFalse(contains_banned_word(""))


if __name__ == "__main__":
    unittest.main()
