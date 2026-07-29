"""Align Observer-detected widgets to Screen Annotation ground-truth elements.

Same matching heuristic `ObserverAgent._refine_with_xml` already uses to
match vision-detected widgets to XML elements (IoU above a threshold, OR
center-distance below a threshold) — reused here rather than inventing a
fresh rule, so the calibration experiment's alignment logic is consistent
with the live pipeline's own widget-matching convention. See
`Dokumen Kepake/DSE Calibration Experiment - Big Plan.md`, Phase 1's
widget-alignment caveat.
"""
import math


def _iou(a: list, b: list) -> float:
    xA, yA = max(a[0], b[0]), max(a[1], b[1])
    xB, yB = min(a[2], b[2]), min(a[3], b[3])
    inter = max(0, xB - xA) * max(0, yB - yA)
    if inter == 0:
        return 0.0
    area_a = (a[2] - a[0]) * (a[3] - a[1])
    area_b = (b[2] - b[0]) * (b[3] - b[1])
    union = area_a + area_b - inter
    return inter / union if union > 0 else 0.0


def _center_dist(a: list, b: list) -> float:
    return math.hypot(
        (a[0] + a[2]) / 2 - (b[0] + b[2]) / 2,
        (a[1] + a[3]) / 2 - (b[1] + b[3]) / 2,
    )


def align_widget_to_ground_truth(widget_bounds: list, ground_truth_elements_px: list,
                                 iou_threshold: float = 0.15, dist_threshold: float = 30.0):
    """Find the Screen Annotation ground-truth element (already scaled to
    pixel coordinates via `screen_annotation_parser.scale_bbox_to_pixels`)
    that best matches a detected widget's bounds.

    Returns the matching element dict ({"type", "text", "bbox"}) or None if
    nothing clears either the IoU or center-distance threshold — a widget
    with no match should be excluded from correctness labeling rather than
    matched to something unrelated.
    """
    best, best_score = None, 0.0
    for el in ground_truth_elements_px:
        if el.get("bbox") is None:
            continue
        score = _iou(widget_bounds, el["bbox"])
        if score > best_score:
            best_score, best = score, el
    if best is not None and best_score > iou_threshold:
        return best

    best_by_dist, best_dist = None, None
    for el in ground_truth_elements_px:
        if el.get("bbox") is None:
            continue
        d = _center_dist(widget_bounds, el["bbox"])
        if best_dist is None or d < best_dist:
            best_dist, best_by_dist = d, el
    if best_by_dist is not None and best_dist is not None and best_dist < dist_threshold:
        return best_by_dist
    return None
