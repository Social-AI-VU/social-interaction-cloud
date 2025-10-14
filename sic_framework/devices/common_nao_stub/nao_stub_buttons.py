"""
NAO stub buttons component.
"""

from sic_framework.core.sensor_python2 import SICSensor
from sic_framework.core.connector import SICConnector
from sic_framework.core.message_python2 import SICMessage, SICConfMessage


class NaoStubButtonsSensor(SICSensor):
    """Stub for NAO button sensor - logs but doesn't generate events."""
    
    @staticmethod
    def get_conf():
        return SICConfMessage()
    
    @staticmethod
    def get_inputs():
        return []
    
    @staticmethod
    def get_output():
        return SICMessage
    
    def execute(self):
        """Buttons don't continuously produce data, so return None."""
        # Stub - no actual button events
        return None

    def stop(self):
        """Stop the Buttons sensor."""
        self._stopped.set()
        super(NaoStubButtonsSensor, self).stop()

class NaoStubButtons(SICConnector):
    component_class = NaoStubButtonsSensor
    
    def register_callback(self, callback):
        """Stub callback registration for buttons."""
        # Get logger from connector
        import logging
        logger = logging.getLogger("NaoStub.buttons")
        logger.info("NaoStub.buttons: Callback registered (no actual button events will be generated)")

