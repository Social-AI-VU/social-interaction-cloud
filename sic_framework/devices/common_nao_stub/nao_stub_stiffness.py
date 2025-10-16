"""
NAO stub stiffness component.
"""

from sic_framework.core.actuator_python2 import SICActuator
from sic_framework.core.connector import SICConnector
from sic_framework.core.message_python2 import SICMessage, SICConfMessage, SICRequest


class NaoStubStiffnessActuator(SICActuator):
    """Stub for NAO stiffness actuator - logs actions instead of executing them."""
    
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
        """Log the stiffness request instead of executing it."""
        self.logger.info("NaoStub.stiffness: {}".format(type(request).__name__))
        self.logger.debug("  Request details: {}".format(request))
        return SICMessage()
    
    def on_message(self, message):
        """Log incoming messages."""
        self.logger.info("NaoStub.stiffness message: {}".format(type(message).__name__))
        self.logger.debug("  Message details: {}".format(message))

    def stop(self):
        """Stop the Stiffness actuator."""
        self._stopped.set()
        super(NaoStubStiffnessActuator, self).stop()


class NaoStubStiffness(SICConnector):
    component_class = NaoStubStiffnessActuator

