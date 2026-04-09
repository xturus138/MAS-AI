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
        def long_click(x: int, y: int) -> str:
            """Perform a long click on x and y coordinates on the device screen."""
            d.long_click(x, y)
            time.sleep(1)
            return f"Successfully long clicked coordinates {x}, {y}"

        @tool
        def type_text(text: str) -> str:
            """Type text into the focused input field using the device keyboard."""
            d.send_keys(text)
            time.sleep(1)
            return f"Successfully typed: {text}"

        @tool
        def swipe_screen(direction: str) -> str:
            """Swipe the screen in a specified direction. Supported: 'up', 'down', 'left', 'right'."""
            d.swipe_ext(direction, scale=0.8)
            time.sleep(1)
            return f"Successfully swiped {direction}"

        @tool
        def start_app(package_name: str) -> str:
            """Launch an application using its package name (e.g., 'com.tokopedia.tkpd')."""
            d.app_start(package_name)
            time.sleep(2)
            return f"Successfully started app: {package_name}"

        @tool
        def stop_app(package_name: str) -> str:
            """Force-stop an application using its package name."""
            d.app_stop(package_name)
            time.sleep(1)
            return f"Successfully stopped app: {package_name}"

        @tool
        def press_back() -> str:
            """Press the system back button."""
            d.press("back")
            time.sleep(1)
            return "Successfully pressed the back button"

        @tool
        def press_home() -> str:
            """Press the system home button to return to the dashboard."""
            d.press("home")
            time.sleep(1)
            return "Successfully pressed the home button"

        @tool
        def press_enter() -> str:
            """Press the enter or search key on the keyboard."""
            d.press("enter")
            time.sleep(1)
            return "Successfully pressed the enter button"

        return [
            click_coordinates, 
            long_click,
            type_text, 
            swipe_screen,
            start_app,
            stop_app,
            press_back,
            press_home,
            press_enter
        ]