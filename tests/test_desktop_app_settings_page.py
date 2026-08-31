from __future__ import annotations

from desktop_app.data.settings import SETTINGS_FIELDS
from desktop_app.pages.settings import RESTART_REQUIRED_FIELDS


def test_every_settings_field_requires_restart():
    assert RESTART_REQUIRED_FIELDS == frozenset(SETTINGS_FIELDS)
