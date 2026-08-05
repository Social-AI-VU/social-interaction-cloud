"""
Local Whisper Speech-to-Text service for SIC.

Runs Whisper large-v3-turbo locally — no internet or API key needed.

Two backends are selected automatically based on the platform:
  - Mac (Apple Silicon): mlx-whisper  (uses Metal GPU via Apple MLX framework)
  - Windows / Linux:     faster-whisper (uses CTranslate2, runs on CPU with int8)

Install the right backend before running:
  Mac:           pip install mlx-whisper
  Windows/Linux: pip install faster-whisper
"""

import platform
import queue
import threading

import numpy as np
import speech_recognition as sr

from sic_framework import SICComponentManager, SICConfMessage
from sic_framework.core.service_python2 import SICService
from sic_framework.core.connector import SICConnector
from sic_framework.core.message_python2 import AudioMessage, SICMessage, SICRequest


class LocalWhisperConf(SICConfMessage):
    """
    Configuration for the LocalWhisper STT service.

    :param language: Language code (e.g. "nl", "en") or None for auto-detect.
    :param model_size: Whisper model to use. Default is "large-v3-turbo".
    :param beam_size: Beam search width — higher is more accurate but slower. Default 5.
    :param task: "transcribe" keeps original language. "translate" converts to English.
    """
    def __init__(
        self,
        language=None,
        model_size="large-v3-turbo",
        beam_size=5,
        task="transcribe",
    ):
        super(SICConfMessage, self).__init__()
        self.language = language
        self.model_size = model_size
        self.beam_size = beam_size
        self.task = task


class GetTranscript(SICRequest):
    """
    Request a transcription from the LocalWhisper service.

    :param timeout: Seconds to wait for speech to start before giving up.
    :param phrase_time_limit: Max seconds of speech to capture before cutting off.
    """
    def __init__(self, timeout=None, phrase_time_limit=None):
        super().__init__()
        self.timeout = timeout
        self.phrase_time_limit = phrase_time_limit


class Transcript(SICMessage):
    """
    Response containing the transcribed text.

    :param transcript: The transcribed text string.
    """
    def __init__(self, transcript):
        super().__init__()
        self.transcript = transcript


class RemoteAudioDevice(sr.AudioSource):
    """
    Wraps a queue of raw PCM bytes as a speech_recognition AudioSource.

    AudioMessage chunks from the robot microphone are written into this queue
    via on_message(). speech_recognition.listen() reads from it to detect
    when speech starts and ends (VAD).
    """

    class Stream:
        def __init__(self, stop_event=None):
            self.queue = queue.Queue()
            self.stop_event = stop_event

        def clear(self):
            with self.queue.mutex:
                self.queue.queue.clear()

        def write(self, data):
            self.queue.put(data)

        def read(self, n_bytes):
            while True:
                if self.stop_event is not None and self.stop_event.is_set():
                    return b""
                try:
                    return self.queue.get(timeout=0.1)
                except queue.Empty:
                    continue

    def __init__(self, sample_rate=16000, sample_width=2, chunk_size=2730, stop_event=None):
        self.SAMPLE_RATE = sample_rate
        self.SAMPLE_WIDTH = sample_width
        self.CHUNK = chunk_size
        self.stream = self.Stream(stop_event=stop_event)


class LocalWhisperComponent(SICService):
    """
    SIC service that transcribes speech locally using Whisper large-v3-turbo.

    Selects faster-whisper or mlx-whisper automatically based on the platform.
    """

    COMPONENT_STARTUP_TIMEOUT = 30

    def __init__(self, *args, **kwargs):
        super(LocalWhisperComponent, self).__init__(*args, **kwargs)

        self._backend = None
        self.model = None
        self._mlx_whisper = None

        if platform.system() == "Darwin":
            try:
                import mlx_whisper as _mlx
                self._mlx_whisper = _mlx
                self._backend = "mlx"
                self.logger.info("LocalWhisper: using mlx-whisper backend (Mac)")
            except ImportError:
                raise ImportError(
                    "mlx-whisper is not installed. Run: pip install mlx-whisper"
                )
        else:
            try:
                from faster_whisper import WhisperModel
                self.model = WhisperModel(
                    self.params.model_size,
                    device="cpu",
                    compute_type="int8",
                )
                self._backend = "faster_whisper"
                self.logger.info("LocalWhisper: using faster-whisper backend (Windows/Linux)")
            except ImportError:
                raise ImportError(
                    "faster-whisper is not installed. Run: pip install faster-whisper"
                )

        self.recognizer = sr.Recognizer()
        self._stream_stop_event = threading.Event()
        self.source = RemoteAudioDevice(stop_event=self._stream_stop_event)
        self.parameters_are_inferred = False

    @staticmethod
    def get_inputs():
        return [AudioMessage, GetTranscript]

    @staticmethod
    def get_output():
        return Transcript

    @staticmethod
    def get_conf():
        return LocalWhisperConf()

    def on_message(self, message):
        """
        Receives raw PCM audio chunks from the robot microphone and
        feeds them into the audio queue for VAD processing.
        """
        if not isinstance(message, AudioMessage):
            return
        if not self.parameters_are_inferred:
            self.source.SAMPLE_RATE = message.sample_rate
            self.source.CHUNK = min(len(message.waveform), self.source.CHUNK)
            self.parameters_are_inferred = True
            self.logger.info(
                "Inferred sample_rate={} chunk_size={}".format(
                    self.source.SAMPLE_RATE, self.source.CHUNK
                )
            )
        self.source.stream.write(message.waveform)

    def on_request(self, request):
        if request.__class__.__name__ != "GetTranscript":
            self.logger.error("Invalid request type: {}".format(type(request)))
            return
        return self.execute(request)

    def execute(self, request):
        """
        1. Clear the audio queue (discard old audio).
        2. Use speech_recognition VAD to capture one phrase.
        3. Convert captured audio to float32 at 16kHz.
        4. Transcribe with faster-whisper or mlx-whisper.
        5. Return Transcript (empty string if silence detected).
        """
        self.source.stream.clear()
        self.logger.info("Listening...")

        audio = self.recognizer.listen(
            self.source,
            timeout=request.timeout,
            phrase_time_limit=request.phrase_time_limit,
        )

        self.logger.info("Transcribing...")

        # Convert captured audio to float32 numpy array at 16kHz [-1.0, 1.0]
        raw = audio.get_raw_data(convert_rate=16000, convert_width=2)
        audio_np = np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0

        if self._backend == "mlx":
            result = self._mlx_whisper.transcribe(
                audio_np,
                path_or_hf_repo="mlx-community/whisper-large-v3-turbo",
                language=self.params.language,
                task=self.params.task,
            )
            transcript_text = result.get("text", "").strip()
            segments = result.get("segments", [])
            no_speech_prob = (
                np.mean([s.get("no_speech_prob", 0.0) for s in segments])
                if segments else 0.0
            )

        else:
            segs, _ = self.model.transcribe(
                audio_np,
                beam_size=self.params.beam_size,
                language=self.params.language,
                task=self.params.task,
            )
            segs = list(segs)
            transcript_text = " ".join(s.text for s in segs).strip()
            no_speech_prob = (
                np.mean([s.no_speech_prob for s in segs])
                if segs else 0.0
            )

        if no_speech_prob > 0.5:
            self.logger.debug("Whisper detected silence")
            return Transcript("")

        self.logger.info("Transcript: " + transcript_text)
        return Transcript(transcript_text)

    def stop(self, *args):
        try:
            self._stream_stop_event.set()
            self.source.stream.write(b"")
        except Exception:
            pass
        super(LocalWhisperComponent, self).stop(*args)


class LocalWhisper(SICConnector):
    """
    Connector for the LocalWhisper STT service.

    Usage:
        whisper = LocalWhisper(ip="127.0.0.1", conf=LocalWhisperConf(language="nl"))
        whisper.connect(robot.microphone)
        result = whisper.request(GetTranscript(timeout=10))
        print(result.transcript)
    """
    component_class = LocalWhisperComponent
    component_group = "LocalWhisper"


def main():
    SICComponentManager([LocalWhisperComponent], component_group="LocalWhisper")


if __name__ == "__main__":
    main()
