from __future__ import annotations

import importlib


def test_desktop_app_module_importable():
    module = importlib.import_module("desktop_app.app")
    assert hasattr(module, "create_app")
    assert callable(module.create_app)
