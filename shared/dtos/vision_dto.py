from typing import List, Optional
from typing_extensions import TypedDict


class BoundingBox(TypedDict):
    x1: int
    y1: int
    x2: int
    y2: int


class DetectedElement(TypedDict):
    id: int
    bounds: List[int]
    cv_bounds: List[int]
    text: str
    type: str
    cls: str
    resource_id: str


class OCRBlock(TypedDict):
    bounds: List[int]
    text: str
    confidence: Optional[float]


class CVElement(TypedDict):
    bounds: List[int]
    type: str
    confidence: Optional[float]


class KeyboardState(TypedDict):
    is_shown: bool


class VisionOutput(TypedDict):
    screenshot_path: str
    annotated_screenshot_path: str
    widgets: List[DetectedElement]
    ocr_blocks: List[OCRBlock]
    cv_elements: List[CVElement]
    keyboard_state: KeyboardState
    image_height: int
    image_width: int


class SemanticEntry(TypedDict):
    id: int
    description: str


class ObserverAnalysis(TypedDict):
    semantic_map: List[SemanticEntry]
    summary: str
    raw_response: str
