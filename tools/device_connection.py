# core/device_connection.py
import uiautomator2 as u2

class DeviceConnection:
    def __init__(self, device_ip):
        self.device_ip = device_ip
        self.d = None

    def connect(self):
        """Membuat satu koneksi utama ke perangkat."""
        print(f"[*] Mencoba terhubung ke perangkat: {self.device_ip}")
        try:
            self.d = u2.connect(self.device_ip)
            print(f"[+] Berhasil terhubung! Serial perangkat: {self.d.serial}")
            return self.d
        except Exception as e:
            print(f"[!] Kritis: Gagal menyambung ke perangkat - {e}")
            return None