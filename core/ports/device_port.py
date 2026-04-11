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
