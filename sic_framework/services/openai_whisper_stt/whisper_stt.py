"""
Speech-to-Text service using OpenAI's Whisper model.

This service uses the OpenAI Whisper model to transcribe audio to text.
"""

import io
import queue

import numpy as np
import speech_recognition as sr
from openai import OpenAI

from sic_framework import SICComponentManager, SICConfMessage
from sic_framework.core.service_python2 import SICService
from sic_framework.core.connector import SICConnector
from sic_framework.core.message_python2 import AudioMessage, SICMessage, SICRequest


class WhisperConf(SICConfMessage):
    """
    Configuration for the OpenAI Whisper STT service.

    Provide either an openai key or a model name to run locally.

    :param openai_key: your secret OpenAI key, see https://platform.openai.com/docs/quickstart
    :type openai_key: str
    :param local_model: Local OpenAI model to use, see https://github.com/openai/whisper#available-models-and-languages
    :type local_model: str
    """

    def __init__(self, openai_key=None, local_model="base.en"):
        super(SICConfMessage, self).__init__()
        self.openai_key = openai_key
        self.model = local_model


class GetTranscript(SICRequest):
    """
    Request to get a transcript from the OpenAI Whisper STT service.

    :param timeout: The maximum number of seconds that this will wait for a phrase to start before giving up and throwing an ``speech_recognition.WaitTimeoutError`` exception. If ``timeout`` is ``None``, there will be no wait timeout.
    :type timeout: float
    :param phrase_time_limit: The maximum number of seconds that this will allow a phrase to continue before stopping and returning the part of the phrase processed before the time limit was reached. The resulting audio will be the phrase cut off at the time limit. If ``phrase_timeout`` is ``None``, there will be no phrase time limit.
    :type phrase_time_limit: float
    """
    def __init__(self, timeout=None, phrase_time_limit=None):
        super().__init__()

        self.timeout = timeout
        self.phrase_time_limit = phrase_time_limit


class Transcript(SICMessage):
    """ 
    Message containing the transcript of the audio.

    :param transcript: The transcript of the audio.
    :type transcript: str
    """
    def __init__(self, transcript):
        super().__init__()
        self.transcript = transcript


class RemoteAudioDevice(sr.AudioSource):
    """
    Audio source for the OpenAI Whisper STT service.

    This class imitates a pyaudio device to use the speech recoginizer API.

    Default parameters are for NAO and Pepper.

    :param sample_rate: The sample rate of the audio.
    :type sample_rate: int
    :param sample_width: The sample width of the audio.
    :type sample_width: int
    :param chunk_size: The chunk size of the audio.
    :type chunk_size: int
    """

    class Stream:
        """
        Stream for the OpenAI Whisper STT service.

        :param queue: The queue for the audio.
        :type queue: queue.Queue
        """
        def __init__(self):
            self.queue = queue.Queue()

        def clear(self):
            with self.queue.mutex:
                self.queue.queue.clear()

        def write(self, bytes):
            self.queue.put(bytes)

        def read(self, n_bytes):
            # todo check n_bytes equeals chunk_size
            return self.queue.get()

    def __init__(self, sample_rate=16000, sample_width=2, chunk_size=2730):

        self.SAMPLE_RATE = sample_rate
        self.SAMPLE_WIDTH = sample_width

        self.CHUNK = chunk_size
        self.stream = self.Stream()


class WhisperComponent(SICService):
    """
    SICService that transcribes audio to text using the OpenAI Whisper model.
    """

    COMPONENT_STARTUP_TIMEOUT = 5

    def __init__(self, *args, **kwargs):
        super(WhisperComponent, self).__init__(*args, **kwargs)

        # self.model = whisper.load_model("base.en")
        if self.params.openai_key:
            self.client = OpenAI(api_key=self.params.openai_key)

        self.recognizer = sr.Recognizer()

        self.source = RemoteAudioDevice()

        self.parameters_are_inferred = False

        self.i = 0

    @staticmethod
    def get_inputs():
        return [AudioMessage, GetTranscript]

    @staticmethod
    def get_output():
        return Transcript

    @staticmethod
    def get_conf():
        return WhisperConf()

    def on_message(self, message):
        """
        Writes audio to the queue.

        :param message: The message to handle.
        :type message: SICMessage
        """
        if not isinstance(message, AudioMessage):
            self.logger.error(f"Invalid message type: {type(message)}")
            return
        if not self.parameters_are_inferred:
            self.source.SAMPLE_RATE = message.sample_rate
            self.source.CHUNK = min(len(message.waveform), self.source.CHUNK)
            self.parameters_are_inferred = True
            self.logger.info(
                "Inferred sample rate: {} and chunk size: {}".format(
                    self.source.SAMPLE_RATE, self.source.CHUNK
                )
            )

        self.source.stream.write(message.waveform)

    def on_request(self, request):
        """
        Get the transcript of the audio.

        :param request: The request to handle.
        :type request: SICRequest
        """
        if not isinstance(request, GetTranscript):
            self.logger.error(f"Invalid request type: {type(request)}")
            return
        else:
            return self.execute(request)

    def execute(self, request):
        """
        Transcribe the audio to text.   

        :param request: The request to execute.
        :type request: GetTranscript
        :return: The transcript of the audio.
        :rtype: Transcript
        """
        self.source.stream.clear()
        self.logger.info("Listening...")
        audio = self.recognizer.listen(
            self.source,
            timeout=request.timeout,
            phrase_time_limit=request.phrase_time_limit,
        )
        self.logger.debug("Transcribing")
        if self.params.openai_key:
            wav_data = io.BytesIO(audio.get_wav_data())
            wav_data.name = "SpeechRecognition_audio.wav"
            response = self.client.audio.transcriptions.create(
                model="whisper-1",
                file=wav_data,
                response_format="verbose_json",
            )
            transcript = response.text
            no_speech_prob = np.mean(
                [segment.no_speech_prob for segment in response.segments]
            )
            self.logger.debug("using online openai model")
        else:
            response = self.recognizer.recognize_whisper(
                audio, language="english", model=self.params.model, show_dict=True
            )
            transcript = response["text"]

            no_speech_prob = np.mean(
                [segment["no_speech_prob"] for segment in response["segments"]]
            )

        if no_speech_prob > 0.5:
            self.logger.debug("Whisper heard silence")
            return Transcript("")
        self.logger.debug("Whisper thinks you said: " + transcript)

        return Transcript(transcript)


class SICWhisper(SICConnector):
    """
    Connector for the OpenAI Whisper STT Component.
    """
    component_class = WhisperComponent


def main():
    """
    Run a ComponentManager that can start the OpenAI Whisper STT Component.
    """
    SICComponentManager([WhisperComponent], name="Whisper")


if __name__ == "__main__":
    main()