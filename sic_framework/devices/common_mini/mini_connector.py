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

    def __init__(self, mini_id):
        #self.mini_id = os.environ.get("ALPHAMINI_ID")
        self.mini_id = mini_id 

    def connect(self):
        MiniSdk.set_log_level(logging.INFO)
        MiniSdk.set_robot_type(MiniSdk.RobotType.EDU)
        # Run the combined async function
        connection_successful = asyncio.run(self._connect_and_enter_program()) # Use the combined function
        if not connection_successful:
             print("Connection or entering program mode failed.")
             raise CouldNotConnectToMiniException(f"Failed during connection/setup for mini {self.mini_id}")
        print("MiniConnector.connect finished successfully.") # Add confirmation

    def disconnect(self):
        # This disconnect logic might also need async review later
        asyncio.run(self._disconnect_to_mini())

    # Combined connection and setup function
    async def _connect_and_enter_program(self):
        device: WiFiDevice = await MiniSdk.get_device_by_name(self.mini_id, 10)
        if not device:
            print(f"Device {self.mini_id} not found during scan.")
            raise CouldNotConnectToMiniException(f"Could not find mini with id {self.mini_id}")

        print(f"Device {self.mini_id} found at {device.address}. Attempting to connect...")
        is_connected = await MiniSdk.connect(device)

        if not is_connected:
            print(f"Failed to establish connection to {device.address}")
            raise CouldNotConnectToMiniException(f"Found mini {self.mini_id} but failed to connect to {device.address}")

        print("Connection successful. Entering programming mode...")
        try:
            # Optional short pause after connect, before enter_program
            # await asyncio.sleep(0.1)
            entered = await MiniSdk.enter_program()
            if entered:
                print("Entered programming mode successfully.")
                return True # Indicate overall success (connected AND in program mode)
            else:
                print("Failed to enter programming mode (enter_program returned False).")
                await MiniSdk.release() # Clean up connection
                raise CouldNotConnectToMiniException(f"Connected to mini {self.mini_id} but failed to enter programming mode.")
        except Exception as e:
            print(f"Error during enter_program: {e}")
            # Attempt cleanup even if enter_program raised an exception (like RuntimeError)
            try:
                await MiniSdk.release()
            except Exception as release_e:
                print(f"Error during release after enter_program failed: {release_e}")
            raise # Re-raise the original exception from enter_program

    async def _disconnect_to_mini(self):
        await MiniSdk.quit_program()
        await MiniSdk.release()

    async def _start_dev_mode(self):
        await MiniSdk.enter_program()
