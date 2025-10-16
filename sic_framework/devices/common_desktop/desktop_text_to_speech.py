import subprocess

from sic_framework import SICActuator, SICComponentManager
from sic_framework.core.connector import SICConnector
from sic_framework.core.message_python2 import (
    AudioMessage,
    SICConfMessage,
    SICMessage,
    TextMessage,
    TextRequest,
)

class TextToSpeechConf(SICConfMessage):
    """
    Parameters for espeak.
    """

    def __init__(
        self,
        amplitude=100,
        pitch=50,
        speed=175,
        gap=0,
        voice="en",
    ):
        """
        Initialize espeak configuration.
        
        :param amplitude: Volume (0-200), default 100
        :param pitch: Pitch adjustment (0-99), default 50
        :param speed: Speed in words per minute, default 175
        :param gap: Word gap in 10ms units, default 0
        :param voice: Voice to use (e.g., 'en', 'en-us', 'en+f3'), default 'en'
        """
        self.amplitude = amplitude
        self.pitch = pitch
        self.speed = speed
        self.gap = gap
        self.voice = voice


class DesktopTextToSpeechActuator(SICActuator):
    """
    Desktop text to speech actuator.

    Requires espeak to be installed.
    """

    def __init__(self, *args, **kwargs):
        super(DesktopTextToSpeechActuator, self).__init__(*args, **kwargs)
        
        # Check if espeak is available
        try:
            subprocess.run(['espeak', '--version'], 
                         capture_output=True, 
                         check=True, 
                         timeout=5)
            self.logger.info("espeak is available")
        except (subprocess.CalledProcessError, FileNotFoundError, subprocess.TimeoutExpired) as e:
            self.logger.warning("espeak not found or not working: {}".format(e))
            self.logger.warning("Please install espeak: 'sudo apt-get install espeak' (Linux) or 'brew install espeak' (macOS)")

    @staticmethod
    def get_conf():
        return TextToSpeechConf()

    @staticmethod
    def get_inputs():
        return [TextMessage, TextRequest]

    @staticmethod
    def get_output():
        return SICMessage

    def _speak(self, text):
        """Use espeak subprocess to speak the text."""
        try:
            # Build espeak command with parameters
            cmd = [
                'espeak',
                '-a', str(self.params.amplitude),  # amplitude (volume)
                '-p', str(self.params.pitch),       # pitch
                '-s', str(self.params.speed),       # speed
                '-g', str(self.params.gap),         # word gap
                '-v', self.params.voice,            # voice
                text
            ]
            
            self.logger.debug("Running espeak command: {}".format(' '.join(cmd)))
            
            # Run espeak and wait for completion
            subprocess.run(cmd, check=True, timeout=30)
            
        except subprocess.CalledProcessError as e:
            self.logger.error("espeak command failed: {}".format(e))
        except subprocess.TimeoutExpired:
            self.logger.error("espeak command timed out")
        except FileNotFoundError:
            self.logger.error("espeak not found. Please install espeak.")

    def on_request(self, request):
        self.logger.debug("Saying: " + request.text)
        self._speak(request.text)
        return SICMessage()

    def on_message(self, message):
        self.logger.debug("Saying: " + message.text)
        self._speak(message.text)

    def stop(self, *args):
        self._stopped.set()
        super(DesktopTextToSpeechActuator, self).stop(*args)

class DesktopTextToSpeech(SICConnector):
    component_class = DesktopTextToSpeechActuator

if __name__ == "__main__":
    SICComponentManager([DesktopTextToSpeechActuator])
