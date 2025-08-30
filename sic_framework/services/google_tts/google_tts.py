"""
Google Text-to-Speech service.

This service uses the Google Text-to-Speech API to convert text to speech.
"""

import io
import wave

from google.cloud import texttospeech as tts
from google.oauth2.service_account import Credentials

from sic_framework import SICComponentManager
from sic_framework.core.service_python2 import SICService
from sic_framework.core.connector import SICConnector
from sic_framework.core.message_python2 import (
    AudioMessage,
    SICConfMessage,
    SICRequest,
)

class Text2SpeechConf(SICConfMessage):
    """
    Configuration message for Google Text-to-Speech.

    Options for language_code, voice_name, and ssml_gender can be found at:
    https://cloud.google.com/text-to-speech/docs/voices

    :param keyfile_json: Path to a google service account json key file, which has access to your dialogflow agent.
    :type keyfile_json: dict
    :param language_code: code to determine the language, as per Google's docs
    :type language_code: str
    :param ssml_gender: code to determine the voice's gender, per Google's docs
    :type ssml_gender: int
    :param voice_name: string that corresponds to one of Google's voice options
    :type voice_name: str
    :param speaking_rate: float that sets the speaking rate of the voice (e.g. 1.0 is normal, 0.5 is slow, 2.0 is fast)
    :type speaking_rate: float
    """
    def __init__(
        self,
        keyfile_json: dict,
        language_code: str = "en-US",
        ssml_gender: int = tts.SsmlVoiceGender.NEUTRAL,
        voice_name: str = "",
        speaking_rate: float = 1.0
    ):
        super(Text2SpeechConf, self).__init__()

        self.keyfile_json = keyfile_json
        self.language_code = language_code
        self.ssml_gender = ssml_gender
        self.voice_name = voice_name
        self.speaking_rate = speaking_rate


class GetSpeechRequest(SICRequest):
    """
    SICRequest to send to SIC Google Text-to-Speech Component.

    The request embeds the text to synthesize and optionally Google voice parameters.

    :param text: the text to synthesize
    :type text: str
    :param language_code: see Text2SpeechConf
    :type language_code: str
    :param voice_name: see Text2SpeechConf
    :type voice_name: str
    :param ssml_gender: see Text2SpeechConf
    :type ssml_gender: int
    :param speaking_rate: see Text2SpeechConf
    :type speaking_rate: float
    """

    def __init__(
        self, text: str, language_code=None, voice_name=None, ssml_gender=None, speaking_rate=None
    ):
        super(GetSpeechRequest, self).__init__()

        self.text = text
        self.language_code = language_code
        self.voice_name = voice_name
        self.ssml_gender = ssml_gender
        self.speaking_rate = speaking_rate


class SpeechResult(AudioMessage):
    """
    Audio message containing the synthesized audio from Google Text-to-Speech.

    :param wav_audio: the synthesized audio
    :type wav_audio: bytes
    """

    def __init__(self, wav_audio):
        self.wav_audio = wav_audio

        # Convert the audio
        audio = wave.open(io.BytesIO(wav_audio))
        sample_rate = audio.getframerate()
        audio_bytes = audio.readframes(audio.getnframes())

        super(SpeechResult, self).__init__(
            waveform=audio_bytes, sample_rate=sample_rate
        )


class Text2SpeechService(SICService):
    """
    Transforms text into a synthesized speech audio.
    """

    def __init__(self, *args, **kwargs):
        super(Text2SpeechService, self).__init__(*args, **kwargs)

        # setup session client using keyfile json
        credentials = Credentials.from_service_account_info(self.params.keyfile_json)
        self.client = tts.TextToSpeechClient(credentials=credentials)

    @staticmethod
    def get_inputs():
        return [GetSpeechRequest]

    @staticmethod
    def get_output():
        return SpeechResult

    @staticmethod
    def get_conf():
        return Text2SpeechConf()
    
    def on_message(self, message):
        """
        Handle input messages.

        The Text2SpeechService doesn't handle any messages.

        :param message: The message to handle.
        :type message: SICMessage
        """
        pass

    def on_request(self, request):
        """
        Handle requests.

        The Text2SpeechService only handles GetSpeechRequests.

        :param request: The request to handle.
        :type request: SICRequest
        """
        if isinstance(request, GetSpeechRequest):
            return self.execute(request)
        else:
            self.logger.error(f"Invalid request type: {type(request)}")
            raise ValueError(f"Invalid request type: {type(request)}")

    def execute(self, request):
        """
        Build the synthesized audio from text within the request.
        
        Calls Google's API and returns the audio in MP3 format within a SpeechResult.

        NOTE: if the GetSpeechRequest does not set a voice parameters, the service's default parameters will be used.

        :param request: GetSpeechRequest, the request with the text to synthesize and optionally voice paramters
        :return: SpeechResult, the response with the synthesized text as audio (MP3 format)
        """
        # Set the text input to be synthesized
        synthesis_input = tts.SynthesisInput(text=request.text)

        # Build the voice request based on request parameters, fall back on service config parameters
        lang_code = (
            request.language_code
            if request.language_code
            else self.params.language_code
        )
        voice_name = (
            request.voice_name if request.voice_name else self.params.voice_name
        )
        ssml_gender = (
            request.ssml_gender if request.ssml_gender else self.params.ssml_gender
        )

        voice = tts.VoiceSelectionParams(
            language_code=lang_code, name=voice_name, ssml_gender=ssml_gender
        )

        speaking_rate = (
            request.speaking_rate if request.speaking_rate else self.params.speaking_rate
        )

        # Select the type of audio file you want returned
        audio_config = tts.AudioConfig(
            audio_encoding=tts.AudioEncoding.LINEAR16,
            speaking_rate=speaking_rate
        )

        # Perform the text-to-speech request
        response = self.client.synthesize_speech(
            input=synthesis_input, voice=voice, audio_config=audio_config
        )

        return SpeechResult(wav_audio=response.audio_content)


class Text2Speech(SICConnector):
    """
    Connector for the SIC Google Text-to-Speech Component.
    """
    component_class = Text2SpeechService


def main():
    """
    Run a ComponentManager that can start the Google Text-to-Speech Component.
    """
    SICComponentManager([Text2SpeechService])


if __name__ == "__main__":
    main()
