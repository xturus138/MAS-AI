import time
from core.ports.device_port import IDeviceClient

class ExecutorTools:
    def __init__(self, device_session: IDeviceClient):
        self.d = device_session

    def click_coordinates(self, x: int, y: int) -> str:
        self.d.click(x, y)
        self.d.wait_idle(timeout=3.0)
        return f"Clicked ({x}, {y})"

    def long_click(self, x: int, y: int) -> str:
        self.d.long_click(x, y)
        self.d.wait_idle(timeout=3.0)
        return f"Long-clicked ({x}, {y})"

    def type_text(self, text: str) -> str:
        self.d.send_keys(text)
        self.d.wait_idle(timeout=3.0)
        return f"Typed: {text}"

    def set_text_by_resource_id(self, resource_id: str, text: str) -> str:
        """Set text directly through uiautomator selector when XML exposes resource-id."""
        if not resource_id or not hasattr(self.d, "d") or self.d.d is None:
            return ""
        try:
            selector = self.d.d(resourceId=resource_id)
            if not selector.exists(timeout=1.0):
                return ""
            selector.set_text(text)
            self.d.wait_idle(timeout=3.0)
            return f"Set text via resource_id {resource_id}: {text}"
        except Exception:
            return ""

    def input_text(self, x: int, y: int, text: str, resource_id: str = "") -> str:
        direct_result = self.set_text_by_resource_id(resource_id, text)
        if direct_result:
            return direct_result
        self.click_coordinates(x, y)
        return self.type_text(text)

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
        self.d.wait_idle(timeout=3.0)
        return f"Swiped {direction}" + (f" in region {region}" if region else " (full screen)")

    def start_app(self, package_name: str) -> str:
        self.d.app_start(package_name)
        self.d.wait_idle(timeout=10.0)
        return f"Started app: {package_name}"

    def stop_app(self, package_name: str) -> str:
        self.d.app_stop(package_name)
        self.d.wait_idle(timeout=5.0)
        return f"Stopped app: {package_name}"

    def press_back(self) -> str:
        self.d.press("back")
        self.d.wait_idle(timeout=3.0)
        return "Pressed back"

    def press_home(self) -> str:
        self.d.press("home")
        self.d.wait_idle(timeout=3.0)
        return "Pressed home"

    def press_enter(self) -> str:
        self.d.press("enter")
        self.d.wait_idle(timeout=3.0)
        return "Pressed enter"

    def check_crash(self, lines: int = 50) -> str:
        """Delegate to device's crash check. Returns '' if no crash or device doesn't support it."""
        return self.d.check_crash(lines)
