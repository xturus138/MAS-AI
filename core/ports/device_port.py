from abc import ABC, abstractmethod
from typing import Optional

class IDeviceClient(ABC):
    @abstractmethod
    def click(self, x: int, y: int):
        pass

    @abstractmethod
    def long_click(self, x: int, y: int):
        pass

    @abstractmethod
    def send_keys(self, text: str):
        pass

    @abstractmethod
    def swipe(self, x1: int, y1: int, x2: int, y2: int):
        pass

    @abstractmethod
    def swipe_ext(self, direction: str, scale: float = 0.8):
        pass

    @abstractmethod
    def app_start(self, package_name: str):
        pass

    @abstractmethod
    def app_stop(self, package_name: str):
        pass

    @abstractmethod
    def press(self, key: str):
        pass

    @abstractmethod
    def screenshot(self, filepath: str):
        pass

    @abstractmethod
    def dump_hierarchy(self) -> str:
        pass

    @abstractmethod
    def wait_idle(self, timeout: float = 10.0):
        """Wait for the device UI to become idle (no pending animations/transitions)."""
        pass

    @abstractmethod
    def check_keyboard_state(self) -> bool:
        """Check if the on-screen keyboard is currently visible."""
        pass

    def shell(self, cmd: str) -> str:
        """Run an ADB shell command and return stdout as a string.
        Default returns empty string — override in real device adapters.
        """
        return ""

    def check_crash(self, lines: int = 50) -> str:
        """Scan the last `lines` logcat error entries for crash signatures.
        Returns the first matching line (max 200 chars) or '' if clean.
        Override in real device adapters.
        """
        return ""

    def get_current_app(self) -> str:
        """Return the package name of the currently foregrounded app, or '' on failure.
        Override in real device adapters.
        """
        return ""
