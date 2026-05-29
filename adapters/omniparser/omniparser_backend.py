import os
import sys
import base64
import cv2


class OmniParserBackend:
    """
    Thin wrapper around Microsoft's OmniParser library.

    Loaded once at ObserverTools init. When OMNIPARSER_ENABLED=true and
    model weights are present, replace both the Canny CV stage and the
    separate EasyOCR call with a single OmniParser call that fuses widget
    detection (YOLO) + icon captioning (Florence-2) + OCR internally.

    Output per widget (before ID assignment):
        {
          'bounds':      [x1, y1, x2, y2],   # absolute pixels
          'cv_bounds':   [x1, y1, x2, y2],   # same (kept for annotate compat)
          'text':        str,                 # OCR text or icon caption
          'type':        'container'|'text_stub',
          'interactivity': bool,
        }

    When unavailable (weights missing, import error, disabled), is_available
    returns False and ObserverTools falls back to the Canny + EasyOCR pipeline.
    """

    def __init__(self, weights_dir: str, project_dir: str, box_threshold: float, enabled: bool):
        self._parser = None
        if enabled:
            self._load(weights_dir, project_dir, box_threshold)
        else:
            print("[OmniParser] Disabled via config (OMNIPARSER_ENABLED=false).")

    def _load(self, weights_dir: str, project_dir: str, box_threshold: float):
        if not weights_dir or not os.path.isdir(weights_dir):
            print(f"[OmniParser] Weights dir not found: {weights_dir!r}. Falling back to Canny.")
            return

        som_path = os.path.join(weights_dir, "icon_detect", "model.pt")
        caption_path = os.path.join(weights_dir, "icon_caption_florence")

        if not os.path.exists(som_path):
            print(f"[OmniParser] YOLO model missing: {som_path}. Falling back to Canny.")
            print("[OmniParser] Download weights with:")
            print("  cd OmniParser && for f in icon_detect/{train_args.yaml,model.pt,model.yaml} icon_caption/{config.json,generation_config.json,model.safetensors}; do huggingface-cli download microsoft/OmniParser-v2.0 \"$f\" --local-dir weights; done && mv weights/icon_caption weights/icon_caption_florence")
            return

        # Insert OmniParser project so its `util` package is importable
        if project_dir and project_dir not in sys.path:
            sys.path.insert(0, project_dir)

        try:
            from util.omniparser import Omniparser  # type: ignore
            cfg = {
                "som_model_path":      som_path,
                "caption_model_name":  "florence2",
                "caption_model_path":  caption_path,
                "BOX_TRESHOLD":        box_threshold,
            }
            self._parser = Omniparser(cfg)
            print("[OmniParser] Backend loaded (YOLO + Florence-2).")
        except Exception as exc:
            print(f"[OmniParser] Load failed: {exc}. Falling back to Canny.")
            self._parser = None

    # ── Public API ──────────────────────────────────────────────────────────

    @property
    def is_available(self) -> bool:
        return self._parser is not None

    def parse_screen(self, image_path: str) -> list:
        """
        Run the full OmniParser pipeline on a screenshot.

        Returns a list of element dicts in MAS AI pre-ID format.
        Raises RuntimeError if backend is not available.
        """
        if not self.is_available:
            raise RuntimeError("OmniParser backend is not loaded.")

        img = cv2.imread(image_path)
        if img is None:
            raise ValueError(f"Cannot read image: {image_path}")
        img_h, img_w = img.shape[:2]

        with open(image_path, "rb") as fh:
            img_b64 = base64.b64encode(fh.read()).decode("utf-8")

        _, parsed_content_list = self._parser.parse(img_b64)

        widgets = []
        status_bar_h = img_h * 0.05  # mirror observer_agent status-bar filter

        for item in parsed_content_list:
            bbox = item.get("bbox", [])
            if len(bbox) != 4:
                continue

            x1 = int(bbox[0] * img_w)
            y1 = int(bbox[1] * img_h)
            x2 = int(bbox[2] * img_w)
            y2 = int(bbox[3] * img_h)

            if x2 <= x1 or y2 <= y1:
                continue
            if y1 < status_bar_h:
                continue

            element_type = item.get("type", "icon")
            content = (item.get("content") or "").strip()

            widgets.append({
                "bounds":       [x1, y1, x2, y2],
                "cv_bounds":    [x1, y1, x2, y2],
                "text":         content,
                "type":         "container" if element_type == "icon" else "text_stub",
                "interactivity": item.get("interactivity", element_type == "icon"),
            })

        return widgets
