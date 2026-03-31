import uiautomator2 as u2

# STEP 1 MANAJEMEN KONEKSI PERANGKAT OTOMATIS //
class DeviceConnection:
    def __init__(self, device_ip):
        self.device_ip = device_ip

    def connect(self):
        print(f"[*] Menghubungkan ke perangkat {self.device_ip} di latar belakang...")
        return u2.connect(self.device_ip)