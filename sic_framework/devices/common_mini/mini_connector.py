import asyncio

import mini.mini_sdk as MiniSdk
from mini.dns.dns_browser import WiFiDevice


# Define a custom exception class
class CouldNotConnectToMiniException(Exception):
    def __init__(self, message):
        # Initialize the custom exception with a message and error code
        super().__init__(message)  # Call the base class constructor


class MiniConnector:

    def __init__(self, mini_id="00167"):
        self.mini_id = mini_id

    def connect(self):
        asyncio.run(self.connect_to_mini())

    async def connect_to_mini(self):
        device: WiFiDevice = await MiniSdk.get_device_by_name(self.mini_id, 10)
        if device:
            return await MiniSdk.connect(device)
        else:
            raise CouldNotConnectToMiniException(f"Could not connect to mini with id {self.mini_id}")