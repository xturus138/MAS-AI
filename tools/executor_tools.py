import time
from langchain_core.tools import tool

# STEP 1 ALAT AKSI KHUSUS EXECUTOR AGENT //
class ExecutorTools:
    def __init__(self, device_session):
        self.d = device_session

    def get_tools(self):
        d = self.d 

        @tool
        def click_coordinates(x: int, y: int) -> str:
            """Klik pada koordinat x dan y di layar perangkat."""
            d.click(x, y)
            time.sleep(1)
            return f"Berhasil menekan koordinat {x}, {y}"

        @tool
        def type_text(text: str) -> str:
            """Mengetik teks menggunakan keyboard perangkat."""
            d.send_keys(text)
            time.sleep(1)
            return f"Berhasil mengetik: {text}"

        @tool
        def press_back() -> str:
            """Menekan tombol kembali (back) pada perangkat."""
            d.press("back")
            time.sleep(1)
            return "Berhasil menekan tombol kembali"

        return [click_coordinates, type_text, press_back]