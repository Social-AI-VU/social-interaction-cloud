"""
Service that transcribes audio to text in real time using the Google Speech-to-Text API.
"""

import threading

from google.cloud.speech_v2 import SpeechClient
from google.cloud.speech_v2.types import cloud_speech as cloud_speech_types

from six.moves import queue

from sic_framework import SICComponentManager
from sic_framework.core.service_python2 import SICService
from sic_framework.core.connector import SICConnector
from sic_framework.core.message_python2 import (
    AudioMessage,
    SICConfMessage,
    SICMessage,
    SICRequest,
)
from sic_framework.core.utils import is_sic_instance


class GoogleSpeechToTextConf(SICConfMessage):
    """
    Configuration for the Google Speech-to-Text API.

    :param keyfile_json         Dict of google service account json key file, which has access to your google
                                project. Example `keyfile_json = json.load(open("my-google-project.json"))`
    :type keyfile_json: dict
    :param sample_rate_hertz    44100Hz by default. Use 16000 for a Nao/Pepper robot.
    :type sample_rate_hertz: int
    :param audio_encoding       encoding for the audio
    :type audio_encoding: cloud_speech_types.ExplicitDecodingConfig.AudioEncoding
    :param language             the language of the Google project
    :type language: str
    :param timeout              the maximum time in seconds to wait for a response from Google. Default is None, which means no timeout,
                                and it will listen indefinitely until it thinks the user is done talking.
    :type timeout: float | None
    :param interim_results      whether to return interim results (when the user is still speaking). Default is True.
    :type interim_results: bool
    :param model                the model to use for the speech recognition. Default is "long".
    :type model: str
    """
    def __init__(
        self,
        keyfile_json: dict,
        sample_rate_hertz: int = 44100,
        audio_encoding=cloud_speech_types.ExplicitDecodingConfig.AudioEncoding.LINEAR16,
        language: str = "en-US",
        timeout: float | None = None,
        interim_results: bool = True,
        model: str = "long",
    ):
        SICConfMessage.__init__(self)

        # init Google variables
        self.language_code = language
        self.project_id = keyfile_json["project_id"]
        self.keyfile_json = keyfile_json
        self.sample_rate_hertz = sample_rate_hertz
        self.audio_encoding = audio_encoding
        self.timeout = timeout
        self.interim_results = interim_results
        self.model = model

class GetStatementRequest(SICRequest):
    def __init__(self):
        """
        Transcribe the next thing the user says.
        """
        super().__init__()

class RecognitionResult(SICMessage):
    """
    Google's recognition of what was said. 
    
    This may take a few different forms. For more information, see:
    https://cloud.google.com/php/docs/reference/cloud-speech/latest/V2.StreamingRecognizeResponse
    
    :param response: the response from Google
    :type response: google.cloud.speech_v2.types.StreamingRecognizeResponse
    """
    def __init__(self, response):
        self.response = response

class GoogleSpeechToTextComponent(SICService):
    """
    SICService that transcribes audio to text using the Google Speech-to-Text API.
    """

    def __init__(self, *args, **kwargs):
        self.responses = None
        super().__init__(*args, **kwargs)
        self.init_google_speech()

    def init_google_speech(self):
        """
        Initialize the Google Speech-to-Text client.
        """
        # setup session client using keyfile json
        self.google_speech_client = SpeechClient.from_service_account_info(self.params.keyfile_json)

        recognition_config = cloud_speech_types.RecognitionConfig(
            explicit_decoding_config=cloud_speech_types.ExplicitDecodingConfig(
                encoding=cloud_speech_types.ExplicitDecodingConfig.AudioEncoding.LINEAR16,
                sample_rate_hertz=self.params.sample_rate_hertz,
                audio_channel_count=1,
            ),
            # NOTE: auto detect decoding causes the bidirectional iterator to hang, so we use explicit decoding for now.
            # auto_decoding_config=cloud_speech_types.AutoDetectDecodingConfig(),
            language_codes=[self.params.language_code],
            model=self.params.model,
        )
        streaming_features = cloud_speech_types.StreamingRecognitionFeatures(
            interim_results=self.params.interim_results,
        )
        streaming_config = cloud_speech_types.StreamingRecognitionConfig(
            config=recognition_config,
            streaming_features=streaming_features,
        )
        self.config_request = cloud_speech_types.StreamingRecognizeRequest(
            recognizer="projects/{project_id}/locations/global/recognizers/_".format(project_id=self.params.project_id),
            streaming_config=streaming_config,
        )

        self.message_was_final = threading.Event()
        self.audio_buffer = queue.Queue(maxsize=1)

    def on_message(self, message):
        """
        Put incoming audio message into the buffer.

        :param message: the audio message
        :type message: AudioMessage
        """
        if is_sic_instance(message, AudioMessage):
            # update the audio message in the queue
            try:
                self.audio_buffer.put_nowait(message.waveform)
            except queue.Full:
                self.audio_buffer.get_nowait()
                self.audio_buffer.put_nowait(message.waveform)
            except Exception as e:
                self.logger.exception("Exception when updating audio buffer: {}".format(e))
                raise e
        else:
            raise NotImplementedError("Unknown message type {}".format(type(message)))

    def on_request(self, request):
        """
        Transcribe the next thing the user says.

        :param request: the request
        :type request: SICRequest
        """
        if is_sic_instance(request, GetStatementRequest):
            return self.get_statement()
        else:
            raise NotImplementedError("Unknown request type {}".format(type(request)))

    def request_generator(self):
        """
        Generate requests to Google Speech-to-Text.
        """
        try:
            # first request to Google needs to be a setup request with the session parameters
            yield self.config_request

            start_time = self._redis.time()

            while not self.message_was_final.is_set():
                if self.params.timeout != None:
                    if self._redis.time() - start_time > self.params.timeout:
                        self.logger.warning(
                            "Request is longer than {timeout} seconds, stopping Google request".format(
                                timeout=self.params.timeout
                            )
                        )
                        self.message_was_final.set()
                        break

                chunk = self.audio_buffer.get()

                if isinstance(chunk, bytearray):
                    chunk = bytes(chunk)

                yield cloud_speech_types.StreamingRecognizeRequest(audio=chunk)

        except Exception as e:
            # log the message instead of gRPC hiding the error, but do crash
            self.logger.exception("Exception in request iterator: {}".format(e))
            raise e

    @staticmethod
    def get_conf():
        return GoogleSpeechToTextConf()

    @staticmethod
    def get_inputs():
        return [GetStatementRequest, AudioMessage]

    @staticmethod
    def get_output():
        return RecognitionResult

    def get_statement(self):
        """
        Listen and get the next statement the user says.

        :return: the recognition result
        :rtype: RecognitionResult
        """
        # unset final message flag
        self.message_was_final.clear()

        # get bi-directional request iterator
        requests = self.request_generator() 

        try:
            responses = self.google_speech_client.streaming_recognize(requests)
        except Exception as e:
            self.logger.error("Exception in get_statement: {}".format(e))
            return RecognitionResult(dict())

        for response in responses:
            if self._stop_event.is_set():
                break

            if not response.results:
                continue

            # The `results` list is consecutive. For streaming, we only care about
            # the first result being considered, since once it's `is_final` is set, it
            # moves on to considering the next utterance.
            result = response.results[0]

            # if there are no alternatives, then there is no transcript, so we skip
            if not result.alternatives:
                continue

            # if the result is not final, then we output the interim result if enabled
            if not result.is_final and self.params.interim_results:
                self.output_message(RecognitionResult(result))
            else:
                # stop the generator function and return the final result
                self.message_was_final.set()
                return RecognitionResult(result)


class GoogleSpeechToText(SICConnector):
    """
    Connector for the Google Speech-to-Text Component.
    """
    component_class = GoogleSpeechToTextComponent


def main():
    """
    Run a ComponentManager that can start the Google Speech-to-Text Component.
    """
    SICComponentManager([GoogleSpeechToTextComponent], name="GoogleSpeechToText")


if __name__ == "__main__":
    main()
