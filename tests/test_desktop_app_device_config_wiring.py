from __future__ import annotations

from unittest.mock import MagicMock, patch

from desktop_app.pages.device_config import connect_device


def test_connect_device_uses_adb_adapter_and_returns_connected_object():
    fake_adapter_instance = MagicMock()
    fake_adapter_instance.connect.return_value = fake_adapter_instance

    with patch("desktop_app.pages.device_config.ADBAdapter", return_value=fake_adapter_instance) as mock_adapter_class:
        result = connect_device("SERIAL123")

    mock_adapter_class.assert_called_once_with("SERIAL123")
    fake_adapter_instance.connect.assert_called_once()
    assert result is fake_adapter_instance


def test_connect_device_propagates_connection_errors():
    fake_adapter_instance = MagicMock()
    fake_adapter_instance.connect.side_effect = RuntimeError("device offline")

    with patch("desktop_app.pages.device_config.ADBAdapter", return_value=fake_adapter_instance):
        try:
            connect_device("SERIAL123")
            assert False, "expected RuntimeError to propagate"
        except RuntimeError as error:
            assert "device offline" in str(error)
