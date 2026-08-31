from __future__ import annotations

import importlib


def test_device_config_page_module_importable():
    module = importlib.import_module("desktop_app.pages.device_config")
    assert hasattr(module, "render_device_config_page")
