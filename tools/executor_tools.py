import time
from core.ports.device_port import IDeviceClient

class ExecutorTools:
    def __init__(self, device_session: IDeviceClient):
        self.d = device_session

    def click_coordinates(self, x: int, y: int) -> str:
        self.d.click(x, y)
        self.d.wait_idle(timeout=5.0)
        time.sleep(1)
        return f"Clicked ({x}, {y})"

    def long_click(self, x: int, y: int) -> str:
        self.d.long_click(x, y)
        self.d.wait_idle(timeout=5.0)
        time.sleep(1)
        return f"Long-clicked ({x}, {y})"

    def type_text(self, text: str) -> str:
        self.d.send_keys(text)
        self.d.wait_idle(timeout=5.0)
        time.sleep(1)
        return f"Typed: {text}"

    def swipe_screen(self, direction: str, region: dict = None) -> str:
        if region:
            cx = (region["x1"] + region["x2"]) // 2
            if direction == "up":
                self.d.swipe(cx, region["y2"], cx, region["y1"])
            elif direction == "down":
                self.d.swipe(cx, region["y1"], cx, region["y2"])
            elif direction == "left":
                cy = (region["y1"] + region["y2"]) // 2
                self.d.swipe(region["x2"], cy, region["x1"], cy)
            elif direction == "right":
                cy = (region["y1"] + region["y2"]) // 2
                self.d.swipe(region["x1"], cy, region["x2"], cy)
        else:
            self.d.swipe_ext(direction, scale=0.8)
        self.d.wait_idle(timeout=5.0)
        time.sleep(1)
        return f"Swiped {direction}" + (f" in region {region}" if region else " (full screen)")

    def start_app(self, package_name: str) -> str:
        self.d.app_start(package_name)
        time.sleep(4) 
        self.d.wait_idle(timeout=10.0)
        time.sleep(1)
        return f"Started app: {package_name}"

    def stop_app(self, package_name: str) -> str:
        self.d.app_stop(package_name)
        time.sleep(1)
        self.d.wait_idle(timeout=5.0)
        time.sleep(1)
        return f"Stopped app: {package_name}"

    def press_back(self) -> str:
        self.d.press("back")
        self.d.wait_idle(timeout=5.0)
        time.sleep(1)
        return "Pressed back"

    def press_home(self) -> str:
        self.d.press("home")
        self.d.wait_idle(timeout=5.0)
        time.sleep(1)
        return "Pressed home"

    def press_enter(self) -> str:
        self.d.press("enter")
        self.d.wait_idle(timeout=5.0)
        time.sleep(1)
        return "Pressed enter"
