import uiautomator2 as u2
from core.ports.device_port import IDeviceClient

class ADBAdapter(IDeviceClient):
    def __init__(self, device_ip):
        self.device_ip = device_ip
        self.d = None

    def connect(self):
        print(f"[*] Connecting to device {self.device_ip}...")
        self.d = u2.connect(self.device_ip)
        return self

    def click(self, x: int, y: int):
        self.d.click(x, y)

    def long_click(self, x: int, y: int):
        self.d.long_click(x, y)

    def send_keys(self, text: str):
        self.d.send_keys(text)

    def swipe(self, x1: int, y1: int, x2: int, y2: int):
        self.d.swipe(x1, y1, x2, y2)

    def swipe_ext(self, direction: str, scale: float = 0.8):
        self.d.swipe_ext(direction, scale=scale)

    def app_start(self, package_name: str):
        self.d.app_start(package_name)

    def app_stop(self, package_name: str):
        self.d.app_stop(package_name)

    def press(self, key: str):
        self.d.press(key)

    def screenshot(self, filepath: str):
        self.d.screenshot(filepath)

    def dump_hierarchy(self) -> str:
        return self.d.dump_hierarchy()

    def wait_idle(self, timeout: float = 10.0):
        try:
            self.d.wait_idle(timeout=timeout)
        except Exception:
            pass  # Timeout is non-fatal; proceed with best effort