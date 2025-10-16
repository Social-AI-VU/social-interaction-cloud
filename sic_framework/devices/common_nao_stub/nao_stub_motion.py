"""
NAO stub motion components.
"""

from sic_framework.core.actuator_python2 import SICActuator
from sic_framework.core.connector import SICConnector
from sic_framework.core.message_python2 import SICMessage, SICConfMessage


class NaoStubMotionActuator(SICActuator):
    """Stub for NAO motion actuator - logs actions instead of executing them."""
    
    @staticmethod
    def get_conf():
        return SICConfMessage()
    
    @staticmethod
    def get_inputs():
        # Accept any NAO motion request
        from sic_framework.core.message_python2 import SICRequest
        return [SICRequest]
    
    @staticmethod
    def get_output():
        return SICMessage
    
    def execute(self, request):
        """Log the motion request instead of executing it."""
        self.logger.info("NaoStub.motion: {}".format(type(request).__name__))
        self.logger.debug("  Request details: {}".format(request))
        return SICMessage()
    
    def on_message(self, message):
        """Log incoming messages."""
        self.logger.info("NaoStub.motion message: {}".format(type(message).__name__))
        self.logger.debug("  Message details: {}".format(message))


class NaoStubMotionRecorderActuator(SICActuator):
    """Stub for NAO motion recorder - logs actions instead of executing them."""
    
    @staticmethod
    def get_conf():
        return SICConfMessage()
    
    @staticmethod
    def get_inputs():
        from sic_framework.core.message_python2 import SICRequest
        return [SICRequest]
    
    @staticmethod
    def get_output():
        return SICMessage
    
    def execute(self, request):
        """Log the motion recorder request instead of executing it."""
        self.logger.info("NaoStub.motion_recorder: {}".format(type(request).__name__))
        self.logger.debug("  Request details: {}".format(request))
        return SICMessage()
    
    def on_message(self, message):
        """Log incoming messages."""
        self.logger.info("NaoStub.motion_recorder message: {}".format(type(message).__name__))
        self.logger.debug("  Message details: {}".format(message))
    
    def stop(self):
        """Stop the Motion recorder actuator."""
        self._stopped.set()
        super(NaoStubMotionRecorderActuator, self).stop()

class NaoStubMotion(SICConnector):
    component_class = NaoStubMotionActuator


class NaoStubMotionRecorder(SICConnector):
    component_class = NaoStubMotionRecorderActuator

