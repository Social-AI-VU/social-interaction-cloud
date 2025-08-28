"""
Google Speech-to-Text API
"""

import threading
import time

import google
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
        """
        :param keyfile_json         Dict of google service account json key file, which has access to your google
                                    project. Example `keyfile_json = json.load(open("my-google-project.json"))`
        :param sample_rate_hertz    44100Hz by default. Use 16000 for a Nao/Pepper robot.
        :param audio_encoding       encoding for the audio
        :param language             the language of the Google project
        :param timeout              the maximum time in seconds to wait for a response from Google. Default is None, which means no timeout,
                                    and it will listen indefinitely until it thinks the user is done talking.
        :param interim_results      whether to return interim results (when the user is still speaking). Default is True.
        :param model                the model to use for the speech recognition. Default is "long".
        """
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


class StopListeningMessage(SICMessage):
    def __init__(self, session_id=0):
        """
        Stop the conversation and determine a last intent. Dialogflow automatically stops listening when it thinks the
        user is done talking, but this can be used to force intent detection as well.
        :param session_id: a (randomly generated) id, but the same one for the whole conversation
        """
        super().__init__()
        self.session_id = session_id

class GetStatementRequest(SICRequest):
    def __init__(self, session_id=0):
        """
        Get the last statement the user said.

        :param session_id: a (randomly generated) id, but the same one for the whole conversation
        """
        super().__init__()
        self.session_id = session_id

class RecognitionResult(SICMessage):
    def __init__(self, response):
        """
        Google's recognition of the conversation up to that point. Is streamed during the execution of the request
        to provide interim results.

        :param response: the response from Google
        :type response: dict

        Example:

        metadata {
        request_id: "696c3874-0000-2d3a-976f-582429aac290"
        }
        results {
            alternatives {
                transcript: "test"
            }
            stability: 0.01
            result_end_offset {
                seconds: 1
                nanos: 560000000
            }
            language_code: "en-US"
            }
            speech_event_offset {
        }

        """
        self.response = response

class GoogleSpeechToTextComponent(SICService):
    """
    Transcribes audio to text.
    """

    def __init__(self, *args, **kwargs):
        self.responses = None
        super().__init__(*args, **kwargs)

        self.google_speech_is_init = False
        self.init_google_speech()

    def init_google_speech(self):
        # Setup session client
        self.google_speech_client = SpeechClient.from_service_account_info(self.params.keyfile_json)

        recognition_config = cloud_speech_types.RecognitionConfig(
            explicit_decoding_config=cloud_speech_types.ExplicitDecodingConfig(
                encoding=cloud_speech_types.ExplicitDecodingConfig.AudioEncoding.LINEAR16,
                sample_rate_hertz=self.params.sample_rate_hertz,
                audio_channel_count=self.params.audio_channel_count,
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
        self.google_speech_is_init = True

    def on_message(self, message):
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
        if not self.google_speech_is_init:
            self.init_google_speech()

        if is_sic_instance(request, GetStatementRequest):
            return self.get_statement()
        elif is_sic_instance(request, StopListeningMessage):
            self.message_was_final.set()
            try:
                del self.google_speech_client
            except AttributeError:
                pass
            self.google_speech_is_init = False
        else:
            raise NotImplementedError("Unknown request type {}".format(type(request)))

    def request_generator(self):
        try:
            # first request to Google needs to be a setup request with the session parameters
            yield self.config_request

            start_time = self._redis.get_time()

            while not self.message_was_final.is_set():
                if self.params.timeout != None:
                    if self._redis.get_time() - start_time > self.params.timeout:
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
        return [GetStatementRequest, StopListeningMessage, AudioMessage]

    @staticmethod
    def get_output():
        return RecognitionResult

    def get_statement(self):
        """
        Listen and get the next statement the user says.
        """
        # unset final message flag
        self.message_was_final.clear()

        # get bi-directional request iterator
        requests = self.request_generator() 

        try:
            responses = self.google_speech_client.streaming_detect_intent(requests)
        except Exception as e:
            self.logger.error("Exception in get_statement: {}".format(e))
            return RecognitionResult(dict())

        for response in responses:
            if self.stop_event.is_set():
                break

            if not response.results:
                continue

            # The `results` list is consecutive. For streaming, we only care about
            # the first result being considered, since once it's `is_final`, it
            # moves on to considering the next utterance.
            result = response.results[0]

            if not result.alternatives:
                continue

            if not result.is_final:
                self.output_message(RecognitionResult(result))
            else:
                # stop the generator function
                self.message_was_final.set()
                return RecognitionResult(result)


class GoogleSpeechToText(SICConnector):
    component_class = GoogleSpeechToTextComponent


def main():
    SICComponentManager([GoogleSpeechToTextComponent], name="GoogleSpeechToText")


if __name__ == "__main__":
    main()
