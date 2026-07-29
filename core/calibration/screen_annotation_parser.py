"""Parser for Google's Screen Annotation dataset label grammar.

The dataset (github.com/google-research-datasets/screen_annotation) stores
one label per screen as a single free-text cell, e.g.:

    TEXT Currency code 79 923 78 111, LIST_ITEM 45 955 116 179
    (RADIO_BUTTON 93 160 129 166, LABEL USD 205 305 131 163), ...

This is NOT JSON and has no published formal grammar in the dataset's own
README (it just says "a description... that identifies UI elements, their
type, position, text, and description"). This parser was reverse-engineered
from the real `train.csv` data, not from an official schema doc — see the
TYPE_VOCAB note below. It should be spot-checked against real output before
being trusted for anything beyond calibration-experiment ground truth (where
the correctness judge, not this parser, is the final arbiter of meaning —
see `Dokumen Kepake/DSE Calibration Experiment - Big Plan.md`, Phase 1).

Grammar (informal): a comma-separated sequence of elements, each shaped
`TYPE [free text] x1 x2 y1 y2`, optionally followed by a parenthesized,
comma-separated list of child elements in the same grammar (e.g. a
LIST_ITEM containing a RADIO_BUTTON and a LABEL). Bounding boxes are in the
dataset's own normalized 0-999 coordinate space, in **(x1, x2, y1, y2)**
order — note this is NOT MAS AI's own `[x1, y1, x2, y2]` widget bounds
order; callers must convert (see `to_xyxy_0_999` below).

TYPE_VOCAB was derived empirically: scanning 5,000 real train.csv rows for
capitalized words appearing where an element header starts, the 14 types
below each occur 100-40,000+ times; every other capitalized word occurring
in that position occurs under 150 times and is indistinguishable from
leaked screen text (state abbreviations, pronouns, drug-name fragments,
etc.). This is a frequency-based inference, not an authoritative list —
cross-check against the ScreenAI paper (Baechler et al. 2024,
arXiv:2402.04615) if a formal schema is ever needed beyond this experiment.
"""
import re

TYPE_VOCAB = {
    "TEXT", "PICTOGRAM", "LIST_ITEM", "BUTTON", "IMAGE", "NAVIGATION_BAR",
    "LABEL", "TOOLBAR", "TEXT_INPUT", "CHECKBOX", "RADIO_BUTTON", "SWITCH",
    "PAGER_INDICATOR", "MAP",
}

_TYPE_HEAD_RE = re.compile(
    r"(" + "|".join(sorted(TYPE_VOCAB, key=len, reverse=True)) + r")\s"
)
_BBOX_RE = re.compile(r"(\d+)\s+(\d+)\s+(\d+)\s+(\d+)\s*$")


def parse_tree(raw: str) -> list:
    """Parse into a nested tree: list of {type, text, bbox, children}.

    bbox is [x1, x2, y1, y2] (dataset's own order, 0-999 normalized) or
    None if no trailing 4-integer bbox was found for that element (rare;
    treated as unparseable-position rather than fabricated).

    Best-effort: if the scanner hits a segment it can't match against
    TYPE_VOCAB, it stops and returns whatever was parsed so far rather than
    guessing at the rest.
    """
    if not raw:
        return []
    pos = 0
    n = len(raw)
    nodes = []
    while pos < n:
        while pos < n and raw[pos] in ", ":
            pos += 1
        if pos >= n or raw[pos] == ")":
            break
        m = _TYPE_HEAD_RE.match(raw, pos)
        if not m:
            break
        etype = m.group(1)
        pos = m.end()

        depth = 0
        i = pos
        header_end = None
        children_start = None
        while i < n:
            c = raw[i]
            if c == "(" and depth == 0:
                children_start = i
                header_end = i
                break
            if c == "(":
                depth += 1
            elif c == ")":
                if depth == 0:
                    header_end = i
                    break
                depth -= 1
            elif c == "," and depth == 0:
                # Only a real element boundary if what follows is a known
                # TYPE keyword — otherwise this is a comma inside free text
                # (e.g. "November 7, 2016").
                look = raw[i + 1:i + 40].lstrip()
                if _TYPE_HEAD_RE.match(look):
                    header_end = i
                    break
            i += 1
        if header_end is None:
            header_end = n

        header = raw[pos:header_end].strip()
        bm = _BBOX_RE.search(header)
        if bm:
            text = header[: bm.start()].strip()
            bbox = [int(bm.group(k)) for k in range(1, 5)]
        else:
            text = header
            bbox = None

        node = {"type": etype, "text": text, "bbox": bbox, "children": []}

        pos = header_end
        if children_start is not None:
            pos += 1  # consume '('
            depth = 1
            start = pos
            while pos < n and depth > 0:
                if raw[pos] == "(":
                    depth += 1
                elif raw[pos] == ")":
                    depth -= 1
                pos += 1
            inner = raw[start: pos - 1]
            node["children"] = parse_tree(inner)

        nodes.append(node)
    return nodes


def flatten(nodes: list) -> list:
    """Flatten a parse_tree() result into a flat list of {type, text, bbox}
    dicts (drops parent/child structure, keeps every element's own bbox)."""
    out = []
    for nd in nodes:
        out.append({"type": nd["type"], "text": nd["text"], "bbox": nd["bbox"]})
        out.extend(flatten(nd["children"]))
    return out


def parse_flat(raw: str) -> list:
    """Convenience: parse_tree() + flatten() in one call."""
    return flatten(parse_tree(raw))


def to_xyxy_0_999(bbox_x1x2y1y2: list) -> list:
    """Convert this dataset's [x1, x2, y1, y2] bbox order to the more
    conventional [x1, y1, x2, y2] order MAS AI's own widgets use (still in
    the dataset's native 0-999 normalized space — see
    `scale_bbox_to_pixels` for converting to actual screenshot pixels)."""
    x1, x2, y1, y2 = bbox_x1x2y1y2
    return [x1, y1, x2, y2]


def scale_bbox_to_pixels(bbox_xyxy_0_999: list, image_width: int, image_height: int) -> list:
    """Scale a [x1, y1, x2, y2] bbox from the dataset's 0-999 normalized
    space to actual pixel coordinates for a screenshot of the given size."""
    x1, y1, x2, y2 = bbox_xyxy_0_999
    return [
        round(x1 / 999.0 * image_width),
        round(y1 / 999.0 * image_height),
        round(x2 / 999.0 * image_width),
        round(y2 / 999.0 * image_height),
    ]
