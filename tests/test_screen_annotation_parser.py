"""Tests for core/calibration/screen_annotation_parser.py.

Fixtures below are verbatim rows copied from the real Screen Annotation
train.csv (screen_ids 11969 and 876), not synthetic examples — this parser
was reverse-engineered from real data (no official grammar spec exists), so
tests must be checked against real data too.
"""
import unittest

from core.calibration.screen_annotation_parser import (
    parse_flat,
    parse_tree,
    scale_bbox_to_pixels,
    to_xyxy_0_999,
)

# Verbatim from train.csv, screen_id=11969.
ROW_11969 = (
    "PICTOGRAM thumbs up 390 607 59 228 (IMAGE a silhouette of a man with "
    "his hand up in the air . 394 603 59 223), TEXT A code has been sent to "
    "+1-4153042067 124 872 254 287, TEXT_INPUT 309 687 300 358 (LABEL Enter "
    "it here 364 633 309 343), TEXT NO CODE? 0 999 826 858 (TEXT NO CODE? "
    "425 570 828 855), NAVIGATION_BAR 0 999 861 935 (BUTTON RESEND 0 496 "
    "861 936, BUTTON CALL ME 503 999 863 936)"
)

# Verbatim from train.csv, screen_id=39382 — includes a comma inside a
# nested LIST_ITEM group, and a LABEL whose text itself is a 3-letter code
# (no embedded comma, but exercises repeated sibling groups).
ROW_39382_PREFIX = (
    "TEXT Currency code 79 923 78 111, LIST_ITEM 45 955 116 179 "
    "(RADIO_BUTTON 93 160 129 166, LABEL USD 205 305 131 163), LIST_ITEM "
    "43 955 181 245 (RADIO_BUTTON 97 157 196 230, LABEL UYU 202 306 198 229)"
)

# Real example of a comma occurring INSIDE free text, not as a separator —
# this is the case the parser must not mis-split on.
ROW_WITH_TEXT_COMMA = (
    "TEXT ETF's with exposure to Dawson Geophysical Co.: November 7, 2016 "
    "62 890 295 359"
)


class TestScreenAnnotationParser(unittest.TestCase):
    def test_flat_parse_row_11969_element_count_and_top_level_types(self):
        flat = parse_flat(ROW_11969)
        types = [el["type"] for el in flat]
        self.assertIn("PICTOGRAM", types)
        self.assertIn("IMAGE", types)
        self.assertIn("TEXT_INPUT", types)
        self.assertIn("LABEL", types)
        self.assertIn("NAVIGATION_BAR", types)
        # 2 BUTTON children under the trailing NAVIGATION_BAR
        self.assertEqual(types.count("BUTTON"), 2)

    def test_pictogram_text_and_bbox(self):
        flat = parse_flat(ROW_11969)
        pictogram = flat[0]
        self.assertEqual(pictogram["type"], "PICTOGRAM")
        self.assertEqual(pictogram["text"], "thumbs up")
        self.assertEqual(pictogram["bbox"], [390, 607, 59, 228])

    def test_nested_children_preserve_own_bbox(self):
        tree = parse_tree(ROW_11969)
        nav_bar = next(n for n in tree if n["type"] == "NAVIGATION_BAR")
        self.assertEqual(len(nav_bar["children"]), 2)
        resend = nav_bar["children"][0]
        self.assertEqual(resend["type"], "BUTTON")
        self.assertEqual(resend["text"], "RESEND")
        self.assertEqual(resend["bbox"], [0, 496, 861, 936])

    def test_repeated_sibling_list_items_both_parsed(self):
        flat = parse_flat(ROW_39382_PREFIX)
        list_items = [el for el in flat if el["type"] == "LIST_ITEM"]
        self.assertEqual(len(list_items), 2)
        labels = [el for el in flat if el["type"] == "LABEL"]
        self.assertEqual([el["text"] for el in labels], ["USD", "UYU"])

    def test_comma_inside_free_text_does_not_split_element(self):
        flat = parse_flat(ROW_WITH_TEXT_COMMA)
        self.assertEqual(len(flat), 1)
        self.assertIn("November 7, 2016", flat[0]["text"])
        self.assertEqual(flat[0]["bbox"], [62, 890, 295, 359])

    def test_empty_string_returns_empty_list(self):
        self.assertEqual(parse_flat(""), [])

    def test_unparseable_remainder_stops_without_raising(self):
        # Deliberately garbled tail with no next-TYPE boundary to split on:
        # the whole remainder becomes this element's free text, and since
        # the bbox regex only matches 4 integers anchored at the very end,
        # no bbox is fabricated from the "1 2 3 4" that isn't actually at
        # the end. This documents the "don't guess" behavior, not a crash.
        garbled = "TEXT Hello 1 2 3 4, this is not a valid element header"
        flat = parse_flat(garbled)
        self.assertEqual(len(flat), 1)
        self.assertEqual(flat[0]["type"], "TEXT")
        self.assertIsNone(flat[0]["bbox"])
        self.assertIn("Hello", flat[0]["text"])

    def test_to_xyxy_0_999_reorders_correctly(self):
        # Dataset order is [x1, x2, y1, y2]; conventional is [x1, y1, x2, y2].
        self.assertEqual(to_xyxy_0_999([10, 90, 20, 80]), [10, 20, 90, 80])

    def test_scale_bbox_to_pixels(self):
        # Full-width/height box in 0-999 space should map to (0,0)-(W,H).
        scaled = scale_bbox_to_pixels([0, 0, 999, 999], image_width=1080, image_height=1920)
        self.assertEqual(scaled, [0, 0, 1080, 1920])


if __name__ == "__main__":
    unittest.main()
