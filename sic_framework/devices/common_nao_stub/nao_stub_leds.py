"""
NAO stub LEDs component.
"""

from sic_framework.core.actuator_python2 import SICActuator
from sic_framework.core.connector import SICConnector
from sic_framework.core.message_python2 import SICMessage, SICConfMessage, SICRequest


class NaoStubLEDsActuator(SICActuator):
    """Stub for NAO LED actuator - logs actions instead of executing them."""
    
    @staticmethod
    def get_conf():
        return SICConfMessage()
    
    @staticmethod
    def get_inputs():
        return [SICRequest]
    
    @staticmethod
    def get_output():
        return SICMessage
    
    def execute(self, request):
        """Log the LED request instead of executing it."""
        self.logger.info("NaoStub.leds: {}".format(type(request).__name__))
        self.logger.debug("  Request details: {}".format(request))
        return SICMessage()
    
    def on_message(self, message):
        """Log incoming messages."""
        self.logger.info("NaoStub.leds message: {}".format(type(message).__name__))
        self.logger.debug("  Message details: {}".format(message))

    def stop(self):
        """Stop the LEDs actuator."""
        self._stopped.set()
        super(NaoStubLEDsActuator, self).stop()

class NaoStubLEDs(SICConnector):
    component_class = NaoStubLEDsActuator

