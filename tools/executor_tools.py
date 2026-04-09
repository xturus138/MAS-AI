import time
from langchain_core.tools import tool

class ExecutorTools:
    def __init__(self, device_session):
        self.d = device_session

    def get_tools(self):
        d = self.d 

        @tool
        def click_coordinates(x: int, y: int) -> str:
            """Click on x and y coordinates on the device screen."""
            d.click(x, y)
            time.sleep(1)
            return f"Successfully clicked coordinates {x}, {y}"

        @tool
        def type_text(text: str) -> str:
            """Type text using the device keyboard."""
            d.send_keys(text)
            time.sleep(1)
            return f"Successfully typed: {text}"

        @tool
        def press_back() -> str:
            """Press the back button on the device."""
            d.press("back")
            time.sleep(1)
            return "Successfully pressed the back button"

        return [click_coordinates, type_text, press_back]