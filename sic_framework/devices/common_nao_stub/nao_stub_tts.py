"""
NAO stub text-to-speech component.
"""

from sic_framework.core.actuator_python2 import SICActuator
from sic_framework.core.connector import SICConnector
from sic_framework.core.message_python2 import SICMessage, SICConfMessage, TextMessage, TextRequest


class NaoStubTTSActuator(SICActuator):
    """Stub for NAO TTS - logs what would be said instead of actually speaking."""
    
    @staticmethod
    def get_conf():
        return SICConfMessage()
    
    @staticmethod
    def get_inputs():
        return [TextMessage, TextRequest]
    
    @staticmethod
    def get_output():
        return SICMessage
    
    def execute(self, request):
        """Log what would be spoken."""
        text = request.text
        self.logger.info("NaoStub.tts: Would say '{}'".format(text))
        return SICMessage()
    
    def on_message(self, message):
        """Handle incoming text messages."""
        if hasattr(message, 'text'):
            self.logger.info("NaoStub.tts: Would say '{}'".format(message.text))

    def stop(self):
        """Stop the TTS actuator."""
        self._stopped.set()
        super(NaoStubTTSActuator, self).stop()


class NaoStubTTS(SICConnector):
    component_class = NaoStubTTSActuator

