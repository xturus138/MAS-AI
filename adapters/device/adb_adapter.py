import uiautomator2 as u2
import cv2
import numpy as np
from core.ports.device_port import IDeviceClient

_CRASH_KEYWORDS = [
    "FATAL EXCEPTION",
    "ANR in",
    "java.lang.",
    "has stopped",
    "NullPointerException",
    "Force close",
]

class ADBAdapter(IDeviceClient):
    def __init__(self, device_ip):
        self.device_ip = device_ip
        self.d = None
        self.scale_x = 1.0
        self.scale_y = 1.0

    def connect(self):
        print(f"[*] Connecting to device {self.device_ip}...")
        self.d = u2.connect(self.device_ip)
        self._calibrate()
        return self

    def _calibrate(self):
        """
        Detects the scaling factor between the native resolution (screenshot) 
        and the logical resolution (input system).
        """
        print("[*] Calibrating coordinate scaling...")
        try:
            
            img = self.d.screenshot(format='opencv')
            if img is not None:
                native_h, native_w = img.shape[:2]
                
                
                logical_w = self.d.info.get('displayWidth')
                logical_h = self.d.info.get('displayHeight')
                
                if logical_w and logical_h:
                    self.scale_x = logical_w / native_w
                    self.scale_y = logical_h / native_h
                    
                    if abs(self.scale_x - 1.0) > 0.01 or abs(self.scale_y - 1.0) > 0.01:
                        print(f"[*] Auto-Scaling Enabled: {self.scale_x:.4f}x (W), {self.scale_y:.4f}x (H)")
                    else:
                        print("[*] Native resolution matches logical resolution (1:1 scaling).")
                else:
                    print("[!] Warning: Could not retrieve logical resolution. Defaulting to 1:1.")
            else:
                print("[!] Warning: Could not take calibration screenshot. Defaulting to 1:1.")
        except Exception as e:
            print(f"[!] Calibration failed: {e}. Defaulting to 1:1.")

    def click(self, x: int, y: int):
        scaled_x, scaled_y = int(x * self.scale_x), int(y * self.scale_y)
        self.d.click(scaled_x, scaled_y)

    def long_click(self, x: int, y: int):
        scaled_x, scaled_y = int(x * self.scale_x), int(y * self.scale_y)
        self.d.long_click(scaled_x, scaled_y)

    def send_keys(self, text: str):
        self.d.send_keys(text)

    def swipe(self, x1: int, y1: int, x2: int, y2: int):
        sx1, sy1 = int(x1 * self.scale_x), int(y1 * self.scale_y)
        sx2, sy2 = int(x2 * self.scale_x), int(y2 * self.scale_y)
        self.d.swipe(sx1, sy1, sx2, sy2)

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
            pass

    def check_keyboard_state(self) -> bool:
        try:
            res = self.d.shell("dumpsys input_method | grep mInputShown")
            return "mInputShown=true" in res.output
        except Exception as e:
            print(f"[!] Failed to check keyboard state: {e}")
            return False

    def shell(self, cmd: str) -> str:
        """Run a shell command via uiautomator2 and return stdout."""
        try:
            res = self.d.shell(cmd)
            return res.output if hasattr(res, "output") else str(res)
        except Exception:
            return ""

    def check_crash(self, lines: int = 50) -> str:
        """Scan last `lines` logcat *:E entries for crash signatures.
        Returns first matching line (max 200 chars) or '' if clean.
        """
        try:
            output = self.shell(f"logcat -d -t {lines} *:E")
            for line in output.splitlines():
                if any(kw in line for kw in _CRASH_KEYWORDS):
                    return line.strip()[:200]
            return ""
        except Exception:
            return ""
