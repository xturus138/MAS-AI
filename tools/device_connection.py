import uiautomator2 as u2

class DeviceConnection:
    def __init__(self, device_ip: str):
        # 1. INITIALIZE DEVICE IP
        self.device_ip = device_ip
        self.d = None

    def connect(self):
        # 2. CONNECT TO DEVICE
        try:
            self.d = u2.connect(self.device_ip)
            return self.d
        except Exception as e:
            print(f"Error: {e}")
            return None