"""
NAO stub tracker and look-at components.
"""

from sic_framework.core.actuator_python2 import SICActuator
from sic_framework.core.connector import SICConnector
from sic_framework.core.message_python2 import SICMessage, SICConfMessage, SICRequest


class NaoStubTrackerActuator(SICActuator):
    """Stub for NAO tracker actuator - logs actions instead of executing them."""
    
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
        """Log the tracker request instead of executing it."""
        self.logger.info("NaoStub.tracker: {}".format(type(request).__name__))
        self.logger.debug("  Request details: {}".format(request))
        return SICMessage()
    
    def on_message(self, message):
        """Log incoming messages."""
        self.logger.info("NaoStub.tracker message: {}".format(type(message).__name__))
        self.logger.debug("  Message details: {}".format(message))

    def stop(self):
        """Stop the Tracker actuator."""
        self._stopped.set()
        super(NaoStubTrackerActuator, self).stop()


class NaoStubLookAtActuator(SICActuator):
    """Stub for NAO look-at actuator - logs actions instead of executing them."""
    
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
        """Log the look-at request instead of executing it."""
        self.logger.info("NaoStub.look_at: {}".format(type(request).__name__))
        self.logger.debug("  Request details: {}".format(request))
        return SICMessage()
    
    def on_message(self, message):
        """Log incoming messages."""
        self.logger.info("NaoStub.look_at message: {}".format(type(message).__name__))
        self.logger.debug("  Message details: {}".format(message))

    def stop(self):
        """Stop the LookAt actuator."""
        self._stopped.set()
        super(NaoStubLookAtActuator, self).stop()

class NaoStubTracker(SICConnector):
    component_class = NaoStubTrackerActuator


class NaoStubLookAt(SICConnector):
    component_class = NaoStubLookAtActuator

