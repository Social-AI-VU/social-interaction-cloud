"""
Google Dialogflow CX (Conversational Agents) service for SIC Framework

This service provides integration with Google's Dialogflow CX API, which is the successor
to Dialogflow ES. It supports bi-directional streaming for real-time conversation processing.

The service accepts audio input and streams it to Dialogflow CX, returning:
- Interim recognition results as the user speaks
- Final query results with detected intents and fulfillment messages

https://cloud.google.com/dialogflow/cx/docs
"""

import threading
import time

import google
from google.cloud import dialogflowcx_v3
from google.oauth2.service_account import Credentials
from six.moves import queue

from sic_framework import SICComponentManager
from sic_framework.core.component_python2 import SICComponent
from sic_framework.core.connector import SICConnector
from sic_framework.core.message_python2 import (
    AudioMessage,
    SICConfMessage,
    SICMessage,
    SICRequest,
)
from sic_framework.core.utils import is_sic_instance


class DetectIntentRequest(SICRequest):
    def __init__(self, session_id=0, parameters=None):
        """
        Request to detect intent from streaming audio input.
        
        Every conversation must use a (semi) unique session ID to maintain conversation context.
        The conversation context is maintained for the duration of the session.
        
        Args:
            session_id: A (randomly generated) unique ID for the conversation session
            parameters: Optional dictionary of parameters to pass to the agent (e.g., custom query parameters)
        """
        super().__init__()
        self.session_id = session_id
        self.parameters = parameters if parameters is not None else {}


class StopListeningMessage(SICMessage):
    def __init__(self, session_id=0):
        """
        Stop the conversation and determine a final intent.
        
        Dialogflow CX automatically stops listening when it detects the user has finished speaking,
        but this message can be used to force intent detection.
        
        Args:
            session_id: The session ID for the conversation to stop
        """
        super().__init__()
        self.session_id = session_id


class RecognitionResult(SICMessage):
    def __init__(self, response):
        """
        Dialogflow CX's understanding of the speech up to that point.
        
        This is streamed during the execution of the request to provide interim results
        as the user is speaking.
        
        Python code example:
            message = RecognitionResult()
            text = message.response.recognition_result.transcript
            is_final = message.response.recognition_result.is_final
            
        Example structure:
            recognition_result {
              message_type: TRANSCRIPT
              transcript: "hello how are you"
              is_final: true
              confidence: 0.95
              language_code: "en-us"
            }
        """
        self.response = response


class QueryResult(SICMessage):
    def __init__(self, response):
        """
        The Dialogflow CX agent's final response.
        
        Python code example:
            message = QueryResult()
            text = message.response.query_result.transcript
            intent_name = message.intent
            fulfillment = message.fulfillment_message
            
        Example data:
            response_id: "abc-123-def-456"
            query_result {
              text: "hello how are you"
              language_code: "en"
              parameters {}
              response_messages {
                text {
                  text: "I'm doing well, thank you for asking!"
                }
              }
              intent {
                name: "projects/.../locations/.../agents/.../intents/..."
                display_name: "greeting.howAreYou"
              }
              intent_detection_confidence: 0.95
              match {
                intent {
                  name: "projects/.../locations/.../agents/.../intents/..."
                  display_name: "greeting.howAreYou"
                }
                confidence: 0.95
              }
            }
        """
        # the raw dialogflow response
        self.response = response

        # helper variables that extract useful data
        self.intent = None
        self.intent_confidence = None
        self.fulfillment_message = None
        self.transcript = None
        self.parameters = {}

        # Extract intent information
        if hasattr(response, 'query_result') and response.query_result:
            qr = response.query_result
            
            # Get transcript
            if hasattr(qr, 'transcript'):
                self.transcript = qr.transcript
            
            # Get intent from match
            if hasattr(qr, 'match') and qr.match:
                if hasattr(qr.match, 'intent') and qr.match.intent:
                    self.intent = qr.match.intent.display_name
                if hasattr(qr.match, 'confidence'):
                    self.intent_confidence = qr.match.confidence
            
            # Get fulfillment text from response messages
            if hasattr(qr, 'response_messages') and len(qr.response_messages) > 0:
                for msg in qr.response_messages:
                    if hasattr(msg, 'text') and msg.text and len(msg.text.text) > 0:
                        self.fulfillment_message = str(msg.text.text[0])
                        break
            
            # Get parameters
            if hasattr(qr, 'parameters') and qr.parameters:
                self.parameters = dict(qr.parameters)


class DialogflowCXConf(SICConfMessage):
    def __init__(
        self,
        keyfile_json: dict,
        agent_id: str,
        location: str = "global",
        sample_rate_hertz: int = 44100,
        audio_encoding=dialogflowcx_v3.AudioEncoding.AUDIO_ENCODING_LINEAR_16,
        language: str = "en-US",
        timeout: float | None = None,
        api_endpoint: str | None = None,
    ):
        """
        Configuration for Dialogflow CX Conversational Agents service.
        
        Args:
            keyfile_json: Dict of Google service account JSON key file with access to your 
                         Dialogflow CX agent. Example: `keyfile_json = json.load(open("my-key.json"))`
            agent_id: The Dialogflow CX agent ID (e.g., "a1b2c3d4-e5f6-g7h8-i9j0-k1l2m3n4o5p6")
            location: The location of your agent (default: "global"). Can also be regional like "us-central1"
            sample_rate_hertz: Audio sample rate in Hz (default: 44100). Use 16000 for Nao/Pepper robots
            audio_encoding: Audio encoding format (default: LINEAR_16)
            language: The language code (default: "en-US")
            timeout: Maximum time in seconds to wait for a response. None means no timeout
            api_endpoint: Regional API endpoint (optional). If None, will be auto-determined from location.
                         Examples: "us-central1-dialogflow.googleapis.com" for us-central1,
                                  "dialogflow.googleapis.com" for global
        """
        SICConfMessage.__init__(self)

        # init Dialogflow CX variables
        self.language_code = language
        self.project_id = keyfile_json["project_id"]
        self.keyfile_json = keyfile_json
        self.agent_id = agent_id
        self.location = location
        self.sample_rate_hertz = sample_rate_hertz
        self.audio_encoding = audio_encoding
        self.timeout = timeout
        
        # Auto-determine API endpoint based on location if not provided
        if api_endpoint is None:
            if location == "global":
                self.api_endpoint = "dialogflow.googleapis.com"
            else:
                # Regional endpoint format: {location}-dialogflow.googleapis.com
                self.api_endpoint = f"{location}-dialogflow.googleapis.com"
        else:
            self.api_endpoint = api_endpoint


class DialogflowCXComponent(SICComponent):
    """
    Dialogflow CX (Conversational Agents) Component for SIC Framework.
    
    This service listens to both AudioMessages and DetectIntentRequests.
    When an intent request is received, it starts streaming audio to Dialogflow CX
    and sends intermediate results as RecognitionResult messages.
    
    Notes:
        - Requires audio chunks of no more than 250ms for smooth interim results
        - Buffer length is 1 to discard audio before we request it to listen
        - The queue enables the generator to wait for new audio messages and yield them to Dialogflow CX
    """

    def __init__(self, *args, **kwargs):
        self.responses = None
        super().__init__(*args, **kwargs)

        self.dialogflow_is_init = False
        self.init_dialogflow()

    def init_dialogflow(self):
        """Initialize the Dialogflow CX client and configuration."""
        # Setup session client with credentials and regional endpoint
        credentials = Credentials.from_service_account_info(self.params.keyfile_json)
        
        # Use region-specific API endpoint
        client_options = {"api_endpoint": self.params.api_endpoint}
        self.session_client = dialogflowcx_v3.SessionsClient(
            credentials=credentials,
            client_options=client_options
        )
        
        self.logger.info(f"Using Dialogflow CX API endpoint: {self.params.api_endpoint}")

        # Set audio input configuration
        self.audio_config = dialogflowcx_v3.InputAudioConfig(
            audio_encoding=self.params.audio_encoding,
            sample_rate_hertz=self.params.sample_rate_hertz,
        )

        # Create AudioInput with the audio config
        audio_input = dialogflowcx_v3.AudioInput(
            config=self.audio_config,
        )

        # Query input configuration for audio
        # In Dialogflow CX, QueryInput needs audio field (not audio_config) and language_code
        self.query_input = dialogflowcx_v3.QueryInput(
            audio=audio_input,
            language_code=self.params.language_code,
        )

        self.message_was_final = threading.Event()
        self.audio_buffer = queue.Queue(maxsize=1)
        self.dialogflow_is_init = True

    def on_message(self, message):
        """Handle incoming messages (audio data or stop commands)."""
        if is_sic_instance(message, AudioMessage):
            # Update the audio message in the queue
            try:
                self.audio_buffer.put_nowait(message.waveform)
            except queue.Full:
                # Replace old audio with new audio if queue is full
                self.audio_buffer.get_nowait()
                self.audio_buffer.put_nowait(message.waveform)

        if is_sic_instance(message, StopListeningMessage):
            # Force the request generator to break, signaling we want an intent
            self.message_was_final.set()
            try:
                del self.session_client
            except AttributeError:
                pass
            self.dialogflow_is_init = False

    def on_request(self, request):
        """Handle intent detection requests."""
        if not self.dialogflow_is_init:
            self.init_dialogflow()

        if is_sic_instance(request, DetectIntentRequest):
            reply = self.detect_intent(request)
            return reply

        raise NotImplementedError("Unknown request type {}".format(type(request)))

    def request_generator(self, session_path):
        """
        Generator that yields streaming requests to Dialogflow CX.
        
        The first request contains session configuration, subsequent requests contain audio data.
        In Dialogflow CX, audio is sent through query_input.audio field, not a separate audio field.
        """
        try:
            # First request: setup with session path and query input configuration
            yield dialogflowcx_v3.StreamingDetectIntentRequest(
                session=session_path,
                query_input=self.query_input,
            )

            start_time = time.time()

            # Subsequent requests: stream audio chunks through query_input.audio
            while not self.message_was_final.is_set():
                # Check timeout if configured
                if self.params.timeout is not None:
                    if time.time() - start_time > self.params.timeout:
                        self.logger.warning(
                            "Request exceeded {timeout} seconds timeout, stopping".format(
                                timeout=self.params.timeout
                            )
                        )
                        self.message_was_final.set()
                        break

                # Get next audio chunk from buffer
                chunk = self.audio_buffer.get()

                # Ensure chunk is bytes
                if isinstance(chunk, bytearray):
                    chunk = bytes(chunk)

                # In Dialogflow CX, audio bytes are sent through QueryInput.audio.audio field
                audio_input = dialogflowcx_v3.AudioInput(audio=chunk)
                query_input = dialogflowcx_v3.QueryInput(
                    audio=audio_input,
                    language_code=self.params.language_code,
                )
                yield dialogflowcx_v3.StreamingDetectIntentRequest(query_input=query_input)

            # Clear flag for next conversation
            self.message_was_final.clear()
        except Exception as e:
            # Log exception (gRPC may hide errors otherwise)
            self.logger.exception("Exception in request iterator")
            raise e

    @staticmethod
    def get_conf():
        return DialogflowCXConf()

    @staticmethod
    def get_inputs():
        return [DetectIntentRequest, StopListeningMessage, AudioMessage]

    @staticmethod
    def get_output():
        return QueryResult

    def detect_intent(self, request):
        """
        Detect intent from streaming audio input.
        
        Args:
            request: DetectIntentRequest containing session_id and optional parameters
            
        Returns:
            QueryResult containing the detected intent and agent response
        """
        self.message_was_final.clear()  # Clear final message flag

        # Construct session path for Dialogflow CX
        # Format: projects/<project>/locations/<location>/agents/<agent>/sessions/<session>
        session_path = (
            f"projects/{self.params.project_id}/"
            f"locations/{self.params.location}/"
            f"agents/{self.params.agent_id}/"
            f"sessions/{request.session_id}"
        )
        
        self.logger.info(
            "Executing Dialogflow CX request with session id {}".format(request.session_id)
        )

        # Get request generator
        requests = self.request_generator(session_path)

        # Make streaming detect intent call
        try:
            responses = self.session_client.streaming_detect_intent(requests=requests)
        except google.api_core.exceptions.NotFound as e:
            error_msg = str(e)
            
            # Check if it's a training issue
            if "NLU model" in error_msg and "does not exist" in error_msg:
                self.logger.error("Agent NLU model not found - Agent needs to be trained!")
                self.logger.error("Error details: {}".format(e))
                self.logger.error("How to fix:")
                self.logger.error("  1. Go to https://dialogflow.cloud.google.com/cx/")
                self.logger.error("  2. Select your agent")
                self.logger.error("  3. Ensure you have intents with training phrases")
                self.logger.error("  4. Click 'Train' and wait for training to complete")
                self.logger.error("  5. Try running the demo again")
            else:
                # Agent not found error
                self.logger.error("Agent not found! Please verify your configuration.")
                self.logger.error("Session path: {}".format(session_path))
                self.logger.error("Error details: {}".format(e))
                self.logger.error("Make sure:")
                self.logger.error("  1. The agent_id is correct")
                self.logger.error("  2. The location matches your agent (try 'global' or a region like 'us-central1')")
                self.logger.error("  3. Your service account has access to the agent")
                self.logger.error("Run verify_dialogflow_cx_agent.py to list available agents")
            return QueryResult(type('obj', (object,), {'query_result': None})())
        except google.api_core.exceptions.InvalidArgument as e:
            self.logger.error("Invalid argument error: {}".format(e))
            return QueryResult(type('obj', (object,), {'query_result': None})())
        except google.api_core.exceptions.PermissionDenied as e:
            self.logger.error("Permission denied! Your service account needs 'Dialogflow API Client' role.")
            self.logger.error("Error details: {}".format(e))
            return QueryResult(type('obj', (object,), {'query_result': None})())
        except Exception as e:
            self.logger.error("Error calling Dialogflow CX: {}".format(e))
            return QueryResult(type('obj', (object,), {'query_result': None})())

        # Process responses
        for response in responses:
            # Handle recognition results (interim transcripts)
            if hasattr(response, 'recognition_result') and response.recognition_result:
                transcript = response.recognition_result.transcript
                if transcript:
                    self.logger.debug("Recognition result: " + transcript)
                    self._redis.send_message(
                        self.component_channel, RecognitionResult(response)
                    )
                
                # Check if this is the final recognition
                if hasattr(response.recognition_result, 'is_final') and response.recognition_result.is_final:
                    self.logger.info("----- FINAL RECOGNITION -----")
                    # Stop sending audio as user stopped speaking
                    self.message_was_final.set()
            
            # Handle query result (final intent detection)
            if hasattr(response, 'detect_intent_response') and response.detect_intent_response:
                dir_response = response.detect_intent_response
                if hasattr(dir_response, 'query_result') and dir_response.query_result:
                    qr = dir_response.query_result
                    if hasattr(qr, 'transcript'):
                        self.logger.info("Received transcript: " + qr.transcript)
                    if hasattr(qr, 'match') and qr.match and hasattr(qr.match, 'intent'):
                        self.logger.info("Detected intent: " + qr.match.intent.display_name)
                    return QueryResult(dir_response)

        # Return empty result if no query result was received
        return QueryResult(type('obj', (object,), {'query_result': None})())

    def stop(self):
        """Stop the component and clean up resources."""
        self.message_was_final.set()
        self.dialogflow_is_init = False
        try:
            del self.session_client
        except AttributeError:
            pass
        except Exception as e:
            self.logger.error("Error deleting session client: {}".format(e))
        self._stopped.set()
        super(DialogflowCXComponent, self).stop()


class DialogflowCX(SICConnector):
    """Connector for the Conversational Agents (Dialogflow CX) component."""
    component_class = DialogflowCXComponent


def main():
    SICComponentManager([DialogflowCXComponent], name="DialogflowCX")


if __name__ == "__main__":
    main()

