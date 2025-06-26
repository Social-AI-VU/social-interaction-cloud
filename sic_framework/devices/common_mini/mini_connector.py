import asyncio
import logging
import os

import mini.mini_sdk as MiniSdk
from mini.dns.dns_browser import WiFiDevice


# Define a custom exception class
class CouldNotConnectToMiniException(Exception):
    def __init__(self, message):
        # Initialize the custom exception with a message and error code
        super().__init__(message)  # Call the base class constructor


class MiniConnector:

    def __init__(self):
        self.mini_id = os.environ.get("ALPHAMINI_ID")

    def connect(self):
        MiniSdk.set_log_level(logging.INFO)
        MiniSdk.set_robot_type(MiniSdk.RobotType.EDU)
        asyncio.run(self._connect_to_mini())

    def disconnect(self):
        asyncio.run(self._disconnect_to_mini())

    async def _connect_to_mini(self):
        device: WiFiDevice = await MiniSdk.get_device_by_name(self.mini_id, 10)
        if device:
            return await MiniSdk.connect(device)
        else:
            raise CouldNotConnectToMiniException("Could not connect to mini with id {mini_id}".format(mini_id=self.mini_id))

    async def _disconnect_to_mini(self):
        await MiniSdk.quit_program()
        await MiniSdk.release()

    async def _start_dev_mode(self):
        await MiniSdk.enter_program()
