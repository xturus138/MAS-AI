"""Shared image utilities for agent vision pipelines.



Both ObserverAgent and ReflectorAgent need to encode screenshots as base64

for multimodal LLM calls. This module consolidates that logic.

"""



import base64

from typing import Optional



import cv2





def encode_image(image_path: str, max_height: int = 720) -> str:

    """Read an image, resize if needed, and encode as base64 WebP (fallback JPEG).



    Args:

        image_path: Path to the image file.

        max_height: Maximum height in pixels. The image is scaled proportionally

                    if its height exceeds this value. Default 720.



    Returns:

        Base64-encoded string, or empty string on failure.

    """

    img = cv2.imread(image_path)

    if img is None:

        return ""



    h, w = img.shape[:2]

    if h > max_height:

        scale = max_height / h

        new_w = int(w * scale)

        img = cv2.resize(img, (new_w, max_height), interpolation=cv2.INTER_AREA)



    success, buffer = cv2.imencode(".webp", img, [int(cv2.IMWRITE_WEBP_QUALITY), 70])

    if not success:

        success, buffer = cv2.imencode(".jpg", img, [int(cv2.IMWRITE_JPEG_QUALITY), 75])

    if not success:

        return ""



    return base64.b64encode(buffer).decode("utf-8")

