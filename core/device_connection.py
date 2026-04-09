import uiautomator2 as u2

class DeviceConnection:
    def __init__(self, device_ip):
        self.device_ip = device_ip

    def connect(self):
        print(f"[*] Connecting to device {self.device_ip} in the background...")
        return u2.connect(self.device_ip)