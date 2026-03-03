"""
ElevenLabs Text-to-Speech service (SIC).

This SIC service supports TWO modes:
1) WebSocket streaming endpoint (low latency): mode="ws"
   - Fixes truncation by collecting all audio chunks until isFinal.
2) HTTP batch endpoint (python-client style): mode="batch"
   - Good for pre-generation / full-text synthesis.

Output format:
- We request PCM output (pcm_<sample_rate>) so the service returns raw PCM bytes.
- We wrap raw PCM bytes into SIC AudioMessage(waveform=..., sample_rate=...).
"""

import os
import asyncio
import base64
import threading
from json import dumps, loads
from typing import Optional, Literal

import requests
import websockets

from sic_framework import SICComponentManager
from sic_framework.core.service_python2 import SICService
from sic_framework.core.connector import SICConnector
from sic_framework.core.message_python2 import AudioMessage, SICConfMessage, SICRequest


# ----------------------------
# SIC Conf / Request / Result
# ----------------------------

class ElevenLabsTTSConf(SICConfMessage):
    """
    Configuration for ElevenLabs TTS.

    Env var fallback supported:
      - ELEVENLABS_API_KEY
      - ELEVENLABS_VOICE_ID
      - ELEVENLABS_MODEL_ID
      - ELEVENLABS_SAMPLE_RATE
      - ELEVENLABS_DEFAULT_MODE  (ws | batch)

    :param api_key: ElevenLabs API key
    :param voice_id: voice id
    :param model_id: model id (e.g., "eleven_flash_v2_5")
    :param sample_rate: used in output_format=pcm_<sample_rate>
    :param speaking_rate: ElevenLabs "speed" (roughly 0.7–1.2)
    :param stability: (0.0–1.0)
    :param default_mode: "ws" or "batch"
    """
    def __init__(
        self,
        api_key: Optional[str] = None,
        voice_id: str = "yO6w2xlECAQRFP6pX7Hw",
        model_id: str = "eleven_flash_v2_5",
        sample_rate: int = 22050,
        speaking_rate: Optional[float] = None,
        stability: float = 0.5,
        default_mode: str = "ws",
    ):
        super(ElevenLabsTTSConf, self).__init__()
        self.api_key = api_key
        self.voice_id = voice_id
        self.model_id = model_id
        self.sample_rate = sample_rate
        self.speaking_rate = speaking_rate
        self.stability = stability
        self.default_mode = default_mode


class GetElevenLabsSpeechRequest(SICRequest):
    """
    Request to synthesize speech.

    :param text: text to synthesize
    :param mode: "ws" (websocket) or "batch" (HTTP)
    :param voice_id/model_id/speaking_rate/stability: optional overrides
    """
    def __init__(
        self,
        text: str,
        mode: Optional[Literal["ws", "batch"]] = None,
        voice_id: Optional[str] = None,
        model_id: Optional[str] = None,
        speaking_rate: Optional[float] = None,
        stability: Optional[float] = None,
    ):
        super(GetElevenLabsSpeechRequest, self).__init__()
        self.text = text
        self.mode = mode
        self.voice_id = voice_id
        self.model_id = model_id
        self.speaking_rate = speaking_rate
        self.stability = stability


class ElevenLabsSpeechResult(AudioMessage):
    """
    Audio message containing synthesized audio.

    We return raw PCM bytes (16-bit mono) as waveform + sample_rate.
    """
    def __init__(self, pcm_audio: bytes, sample_rate: int):
        super(ElevenLabsSpeechResult, self).__init__(waveform=pcm_audio, sample_rate=sample_rate)


# ----------------------------
# Async bridge for SIC execute()
# ----------------------------

def run_coro_sync(coro):
    """
    Run an async coroutine from synchronous code safely.

    - If no loop is running: asyncio.run
    - If a loop is already running: run in a dedicated thread + event loop
    """
    try:
        loop = asyncio.get_running_loop()
        loop_running = loop.is_running()
    except RuntimeError:
        loop_running = False

    if not loop_running:
        return asyncio.run(coro)

    result_container = {"result": None, "error": None}
    done = threading.Event()

    def _thread_main():
        try:
            tloop = asyncio.new_event_loop()
            asyncio.set_event_loop(tloop)
            result_container["result"] = tloop.run_until_complete(coro)
        except Exception as e:
            result_container["error"] = e
        finally:
            try:
                tloop.stop()
                tloop.close()
            except Exception:
                pass
            done.set()

    t = threading.Thread(target=_thread_main, daemon=True)
    t.start()
    done.wait()

    if result_container["error"] is not None:
        raise result_container["error"]
    return result_container["result"]


# ----------------------------
# ElevenLabs WebSocket client
# ----------------------------

class ElevenLabsWSClient:
    """
    WebSocket stream-input endpoint client.
    Fixes truncation by collecting all audio chunks until isFinal.
    """
    def __init__(
        self,
        api_key: str,
        voice_id: str,
        model_id: str,
        sample_rate: int = 22050,
        speaking_rate: Optional[float] = None,
        stability: float = 0.5,
        inactivity_timeout: int = 180,
    ):
        self.api_key = api_key
        self.voice_id = voice_id
        self.model_id = model_id
        self.sample_rate = sample_rate
        self.speaking_rate = speaking_rate
        self.stability = stability
        self.inactivity_timeout = inactivity_timeout
        self.websocket = None

    async def connect(self):
        uri = (
            f"wss://api.elevenlabs.io/v1/text-to-speech/{self.voice_id}/stream-input"
            f"?model_id={self.model_id}"
            f"&output_format=pcm_{self.sample_rate}"
            f"&inactivity_timeout={self.inactivity_timeout}"
            f"&auto_mode=false"
        )
        self.websocket = await websockets.connect(uri)

        voice_settings = {
            "stability": self.stability,
            "similarity_boost": 0.8,
            "use_speaker_boost": False,
            "chunk_length_schedule": [120, 160, 250, 290],
        }
        if self.speaking_rate is not None:
            voice_settings["speed"] = self.speaking_rate

        # initial config message
        await self.websocket.send(dumps({
            "text": " ",
            "voice_settings": voice_settings,
            "auto_mode": True,
            "xi_api_key": self.api_key,
        }))

    async def close(self):
        if self.websocket:
            try:
                await self.websocket.send(dumps({"text": ""}))  # end marker
                await self.websocket.close()
            finally:
                self.websocket = None

    async def synthesize_pcm(self, text: str, recv_timeout_s: float = 20.0) -> bytes:
        if not self.websocket or self.websocket.closed:
            await self.connect()

        await self.websocket.send(dumps({"text": text, "flush": True}))

        chunks = []
        while True:
            msg = await asyncio.wait_for(self.websocket.recv(), timeout=recv_timeout_s)
            data = loads(msg)

            if data.get("audio"):
                chunks.append(base64.b64decode(data["audio"]))

            if data.get("isFinal"):
                break

        return b"".join(chunks)


# ----------------------------
# ElevenLabs HTTP (batch) client
# ----------------------------

class ElevenLabsHTTPClient:
    """
    Batch (non-websocket) synthesis via ElevenLabs HTTP API.

    This is effectively what the "Python client" wraps.
    We request PCM output format so it matches SIC AudioMessage waveform usage.

    Note: If your ElevenLabs account/endpoint doesn't support the specific output_format,
    switch to "mp3_44100_128" etc., then you'll need to decode to PCM before returning.
    """
    def __init__(
        self,
        api_key: str,
        voice_id: str,
        model_id: str,
        sample_rate: int = 22050,
        speaking_rate: Optional[float] = None,
        stability: float = 0.5,
    ):
        self.api_key = api_key
        self.voice_id = voice_id
        self.model_id = model_id
        self.sample_rate = sample_rate
        self.speaking_rate = speaking_rate
        self.stability = stability

    def synthesize_pcm(self, text: str, timeout_s: float = 30.0) -> bytes:
        url = f"https://api.elevenlabs.io/v1/text-to-speech/{self.voice_id}"
        params = {
            "output_format": f"pcm_{self.sample_rate}",
        }
        headers = {
            "xi-api-key": self.api_key,
            "accept": "application/octet-stream",
            "content-type": "application/json",
        }

        voice_settings = {
            "stability": self.stability,
            "similarity_boost": 0.8,
            "use_speaker_boost": False,
        }
        if self.speaking_rate is not None:
            voice_settings["speed"] = self.speaking_rate

        payload = {
            "text": text,
            "model_id": self.model_id,
            "voice_settings": voice_settings,
        }

        resp = requests.post(url, params=params, headers=headers, json=payload, timeout=timeout_s)
        resp.raise_for_status()
        return resp.content


# ----------------------------
# SIC Service + Connector
# ----------------------------

class ElevenLabsTTSService(SICService):
    """
    SIC ElevenLabs TTS service.

    Handles GetElevenLabsSpeechRequest and returns ElevenLabsSpeechResult (AudioMessage).
    """

    def __init__(self, *args, **kwargs):
        super(ElevenLabsTTSService, self).__init__(*args, **kwargs)

        # Env fallbacks
        if not getattr(self.params, "api_key", None):
            self.params.api_key = os.getenv("ELEVENLABS_API_KEY", "")

        if getattr(self.params, "voice_id", None) in (None, ""):
            self.params.voice_id = os.getenv("ELEVENLABS_VOICE_ID", "yO6w2xlECAQRFP6pX7Hw")

        if getattr(self.params, "model_id", None) in (None, ""):
            self.params.model_id = os.getenv("ELEVENLABS_MODEL_ID", "eleven_flash_v2_5")

        if getattr(self.params, "sample_rate", None) in (None, 0):
            self.params.sample_rate = int(os.getenv("ELEVENLABS_SAMPLE_RATE", "22050"))

        if getattr(self.params, "default_mode", None) in (None, ""):
            self.params.default_mode = os.getenv("ELEVENLABS_DEFAULT_MODE", "ws")

        if not self.params.api_key:
            self.logger.warning("[ElevenLabsTTS] No API key found in conf or ELEVENLABS_API_KEY env var.")

    @staticmethod
    def get_inputs():
        return [GetElevenLabsSpeechRequest]

    @staticmethod
    def get_output():
        return ElevenLabsSpeechResult

    @staticmethod
    def get_conf():
        return ElevenLabsTTSConf()

    def on_message(self, message):
        # request-driven service
        pass

    def on_request(self, request):
        if isinstance(request, GetElevenLabsSpeechRequest):
            return self.execute(request)
        self.logger.error(f"Invalid request type: {type(request)}")
        raise ValueError(f"Invalid request type: {type(request)}")

    def execute(self, request: GetElevenLabsSpeechRequest):
        # Resolve params: request overrides > service config
        voice_id = request.voice_id if request.voice_id else self.params.voice_id
        model_id = request.model_id if request.model_id else self.params.model_id
        speaking_rate = request.speaking_rate if request.speaking_rate is not None else self.params.speaking_rate
        stability = request.stability if request.stability is not None else self.params.stability
        sample_rate = int(self.params.sample_rate)

        # Clamp speaking_rate if provided
        if speaking_rate is not None:
            speaking_rate = max(0.7, min(float(speaking_rate), 1.2))

        mode = request.mode if request.mode else getattr(self.params, "default_mode", "ws")
        mode = mode.lower().strip()

        if mode not in ("ws", "batch"):
            raise ValueError(f"Invalid mode '{mode}'. Use 'ws' or 'batch'.")

        if mode == "batch":
            # HTTP (python-client style) synthesis
            client = ElevenLabsHTTPClient(
                api_key=self.params.api_key,
                voice_id=voice_id,
                model_id=model_id,
                sample_rate=sample_rate,
                speaking_rate=speaking_rate,
                stability=float(stability),
            )
            pcm_audio = client.synthesize_pcm(request.text)
            return ElevenLabsSpeechResult(pcm_audio=pcm_audio, sample_rate=sample_rate)

        # WebSocket streaming synthesis (collect until isFinal)
        ws_client = ElevenLabsWSClient(
            api_key=self.params.api_key,
            voice_id=voice_id,
            model_id=model_id,
            sample_rate=sample_rate,
            speaking_rate=speaking_rate,
            stability=float(stability),
        )

        async def _do():
            try:
                pcm = await ws_client.synthesize_pcm(request.text)
                return pcm
            finally:
                await ws_client.close()

        pcm_audio = run_coro_sync(_do())
        return ElevenLabsSpeechResult(pcm_audio=pcm_audio, sample_rate=sample_rate)

    def stop(self):
        self._stopped.set()
        super(ElevenLabsTTSService, self).stop()


class ElevenLabsTTS(SICConnector):
    component_class = ElevenLabsTTSService


def main():
    SICComponentManager([ElevenLabsTTSService], name="ElevenLabsTTS")


if __name__ == "__main__":
    main()





'''''

"""
ElevenLabs service.

This service uses the ElevenLabs API to convert text to speech.
"""

import io
import wave
import asyncio
import base64
from json import dumps, loads
import websockets

from sic_framework import SICComponentManager
from sic_framework.core.service_python2 import SICService
from sic_framework.core.connector import SICConnector
from sic_framework.core.message_python2 import (
    AudioMessage,
    SICConfMessage,
    SICRequest,
)

class ElevenLabsTTSConf(SICConfMessage):
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
        api_key: str,
        voice_id: str,
        model_id: str,
        sample_rate: int = 22050,
        speaking_rate: float = 1.0
    ):
        super(ElevenLabsTTSConf, self).__init__()

        self.api_key = api_key
        self.voice_id = voice_id
        self.model_id = model_id
        self.sample_rate = sample_rate
        self.speaking_rate = speaking_rate


class GetElevenLabsSpeechRequest(SICRequest):
    """
    SICRequest to send to SIC Google Text-to-Speech Component.

    The request embeds the text to synthesize and optionally Google voice parameters.

    :param text: the text to synthesize
    :type text: str
    :param language_code: see ElevenLabsTTSConf
    :type language_code: str
    :param voice_name: see ElevenLabsTTSConf
    :type voice_name: str
    :param ssml_gender: see ElevenLabsTTSConf
    :type ssml_gender: int
    :param speaking_rate: see ElevenLabsTTSConf
    :type speaking_rate: float
    """

    def __init__(
        self, text: str, voice_id=None, model_id=None, speaking_rate=None
    ):
        super(GetElevenLabsSpeechRequest, self).__init__()

        self.text = text
        self.voice_id = voice_id
        self.model_id = model_id
        self.speaking_rate = speaking_rate


class ElevenLabsSpeechResult(AudioMessage):
    """
    Audio message containing the synthesized audio from Google Text-to-Speech.

    :param wav_audio: the synthesized audio
    :type wav_audio: bytes
    """

    def __init__(self, pcm_audio: bytes, sample_rate: int):
        self.pcm_audio = pcm_audio
        self.sample_rate = sample_rate

        super(ElevenLabsSpeechResult, self).__init__(
            waveform=pcm_audio, sample_rate=sample_rate
        )


class ElevenLabsTTSService(SICService):
    """
    Transforms text into a synthesized speech audio.
    """

    def __init__(self, *args, **kwargs):
        super(ElevenLabsTTSService, self).__init__(*args, **kwargs)

        # setup session client using keyfile json

    @staticmethod
    def get_inputs():
        return [GetElevenLabsSpeechRequest]

    @staticmethod
    def get_output():
        return ElevenLabsSpeechResult

    @staticmethod
    def get_conf():
        return ElevenLabsTTSConf()
    
    def on_message(self, message):
        """
        Handle input messages.

        The ElevenLabsTTSService doesn't handle any messages.

        :param message: The message to handle.
        :type message: SICMessage
        """
        pass

    def on_request(self, request):
        """
        Handle requests.

        The ElevenLabsTTSService only handles GetElevenLabsSpeechRequests.

        :param request: The request to handle.
        :type request: SICRequest
        """
        if isinstance(request, GetElevenLabsSpeechRequest):
            return self.execute(request)
        else:
            self.logger.error(f"Invalid request type: {type(request)}")
            raise ValueError(f"Invalid request type: {type(request)}")

    def execute(self, request):
        """
        Build the synthesized audio from text within the request.
        
        Calls Google's API and returns the audio in MP3 format within a ElevenLabsSpeechResult.

        NOTE: if the GetElevenLabsSpeechRequest does not set a voice parameters, the service's default parameters will be used.

        :param request: GetElevenLabsSpeechRequest, the request with the text to synthesize and optionally voice paramters
        :return: ElevenLabsSpeechResult, the response with the synthesized text as audio (MP3 format)
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

        return ElevenLabsSpeechResult(wav_audio=response.audio_content)

    def stop(self, *args):
        """
        Stop the ElevenLabsTTSService.
        """
        super(ElevenLabsTTSService, self).stop(*args)

    def _cleanup(self):
        try:
            client = getattr(self, "client", None)
            if client is not None and hasattr(client, "close"):
                client.close()
        except Exception:
            pass


class ElevenLabsTTS(SICConnector):
    """
    Connector for the SIC Google Text-to-Speech Component.
    """
    component_class = ElevenLabsTTSService


def main():
    """
    Run a ComponentManager that can start the Google Text-to-Speech Component.
    """
    SICComponentManager([ElevenLabsTTSService], name="ElevenLabsTTS")


if __name__ == "__main__":
    main()
'''