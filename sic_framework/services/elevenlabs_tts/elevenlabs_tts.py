"""
ElevenLabs Text-to-Speech service (SIC).

This SIC service supports TWO modes:
1) WebSocket streaming endpoint (low latency): mode="ws"
   - Collects all audio chunks until isFinal, then returns one final AudioMessage.
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
        super(ElevenLabsSpeechResult, self).__init__(
            waveform=pcm_audio,
            sample_rate=sample_rate,
        )


def run_coro_sync(coro, timeout=25.0):
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
                tloop.close()
            except Exception:
                pass
            done.set()

    t = threading.Thread(target=_thread_main, daemon=True)
    t.start()
    finished = done.wait(timeout=timeout)

    if not finished:
        raise RuntimeError("run_coro_sync timed out after {}s".format(timeout))

    if result_container["error"] is not None:
        raise result_container["error"]
    return result_container["result"]




class ElevenLabsWSClient:
    """
    WebSocket stream-input endpoint client.
    Collects all audio chunks until isFinal.
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
        self.websocket = await asyncio.wait_for(websockets.connect(uri), timeout=15.0)

        voice_settings = {
            "stability": self.stability,
            "similarity_boost": 0.8,
            "use_speaker_boost": False,
            "chunk_length_schedule": [120, 160, 250, 290],
        }
        if self.speaking_rate is not None:
            voice_settings["speed"] = self.speaking_rate

        await self.websocket.send(dumps({
            "text": " ",
            "voice_settings": voice_settings,
            "auto_mode": False,
            "xi_api_key": self.api_key,
        }))

    async def close(self):
        if self.websocket:
            try:
                await self.websocket.close()
            finally:
                self.websocket = None

    async def synthesize_pcm(self, text: str, recv_timeout_s: float = 20.0) -> bytes:
        if not self.websocket or self.websocket.closed:
            await self.connect()

        await self.websocket.send(dumps({"text": text}))
        await self.websocket.send(dumps({"text": ""}))
        ws = self.websocket
        self.websocket = None  # stream is closed, force reconnect next call

        chunks = []
        while True:
            msg = await asyncio.wait_for(
                ws.recv(),
                timeout=recv_timeout_s,
            )
            data = loads(msg)

            if data.get("audio"):
                chunks.append(base64.b64decode(data["audio"]))

            if data.get("isFinal"):
                break

        pcm_audio = b"".join(chunks)
        if not pcm_audio:
            raise RuntimeError("ElevenLabs WebSocket API returned empty audio.")

        return pcm_audio



class ElevenLabsHTTPClient:
    """
    Batch (non-websocket) synthesis via ElevenLabs HTTP API.

    We request PCM output format so it matches SIC AudioMessage waveform usage.
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

        resp = requests.post(
            url,
            params=params,
            headers=headers,
            json=payload,
            timeout=timeout_s,
        )
        resp.raise_for_status()

        if not resp.content:
            raise RuntimeError("ElevenLabs HTTP API returned empty audio.")

        return resp.content



class ElevenLabsTTSService(SICService):
    """
    SIC ElevenLabs TTS service.

    Handles GetElevenLabsSpeechRequest and returns ElevenLabsSpeechResult.
    """

    def __init__(self, *args, **kwargs):
        super(ElevenLabsTTSService, self).__init__(*args, **kwargs)

        if not getattr(self.params, "api_key", None):
            self.params.api_key = os.getenv("ELEVENLABS_API_KEY", "")

        if getattr(self.params, "voice_id", None) in (None, ""):
            self.params.voice_id = os.getenv(
                "ELEVENLABS_VOICE_ID",
                "yO6w2xlECAQRFP6pX7Hw",
            )

        if getattr(self.params, "model_id", None) in (None, ""):
            self.params.model_id = os.getenv(
                "ELEVENLABS_MODEL_ID",
                "eleven_flash_v2_5",
            )

        if getattr(self.params, "sample_rate", None) in (None, 0):
            self.params.sample_rate = int(
                os.getenv("ELEVENLABS_SAMPLE_RATE", "22050")
            )

        if getattr(self.params, "default_mode", None) in (None, ""):
            self.params.default_mode = os.getenv(
                "ELEVENLABS_DEFAULT_MODE",
                "ws",
            )

        if not self.params.api_key:
            self.logger.warning(
                "[ElevenLabsTTS] No API key found in conf or "
                "ELEVENLABS_API_KEY env var."
            )

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
        pass

    def on_request(self, request):
        if (
            request.__class__.__name__ == "GetElevenLabsSpeechRequest"
            and hasattr(request, "text")
        ):
            return self.execute(request)

        self.logger.error("Invalid request type: {}".format(type(request)))
        raise ValueError("Invalid request type: {}".format(type(request)))

    def execute(self, request: GetElevenLabsSpeechRequest):
        if not self.params.api_key:
            raise ValueError("No ElevenLabs API key configured.")

        if not request.text or not request.text.strip():
            raise ValueError("Request text must be non-empty.")

        voice_id = request.voice_id if request.voice_id else self.params.voice_id
        model_id = request.model_id if request.model_id else self.params.model_id
        speaking_rate = (
            request.speaking_rate
            if request.speaking_rate is not None
            else self.params.speaking_rate
        )
        stability = (
            request.stability
            if request.stability is not None
            else self.params.stability
        )
        sample_rate = int(self.params.sample_rate)

        if speaking_rate is not None:
            speaking_rate = max(0.7, min(float(speaking_rate), 1.2))

        mode = request.mode if request.mode else getattr(
            self.params,
            "default_mode",
            "ws",
        )
        mode = mode.lower().strip()

        if mode not in ("ws", "batch"):
            raise ValueError("Invalid mode '{}'. Use 'ws' or 'batch'.".format(mode))

        self.logger.info(
            "Synthesizing speech with mode={}, voice_id={}, model_id={}, sample_rate={}".format(
                mode,
                voice_id,
                model_id,
                sample_rate,
            )
        )

        if mode == "batch":
            client = ElevenLabsHTTPClient(
                api_key=self.params.api_key,
                voice_id=voice_id,
                model_id=model_id,
                sample_rate=sample_rate,
                speaking_rate=speaking_rate,
                stability=float(stability),
            )
            pcm_audio = client.synthesize_pcm(request.text)

            if not pcm_audio:
                raise RuntimeError(
                    "ElevenLabs returned empty audio in batch mode."
                )

            self.logger.info("Generated {} bytes of PCM audio".format(len(pcm_audio)))
            return ElevenLabsSpeechResult(
                pcm_audio=pcm_audio,
                sample_rate=sample_rate,
            )

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
                return await ws_client.synthesize_pcm(request.text)
            finally:
                await ws_client.close()

        pcm_audio = run_coro_sync(_do())

        if not pcm_audio:
            raise RuntimeError(
                "ElevenLabs returned empty audio in websocket mode."
            )

        self.logger.info(f"Generated {len(pcm_audio)} bytes of PCM audio")
        return ElevenLabsSpeechResult(
            pcm_audio=pcm_audio,
            sample_rate=sample_rate,
        )

    def stop(self):
        self._stopped.set()
        super(ElevenLabsTTSService, self).stop()


class ElevenLabsTTS(SICConnector):
    component_class = ElevenLabsTTSService
    component_group = "ElevenLabsTTS"


def main():
    SICComponentManager([ElevenLabsTTSService], component_group="ElevenLabsTTS")


if __name__ == "__main__":
    main()