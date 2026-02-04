"""
Voice Detection service using Silero VAD (Voice Activity Detection).

This service uses the Silero VAD model to detect whether human speech is present in audio streams.
It continuously processes audio input and outputs messages when speech activity is detected or stops.
"""

import threading
import time

import numpy as np
import torch
import torchaudio

from sic_framework import SICComponentManager, SICConfMessage
from sic_framework.core.service_python2 import SICService
from sic_framework.core.connector import SICConnector
from sic_framework.core.message_python2 import AudioMessage, SICMessage


class VoiceDetectionConf(SICConfMessage):
    """
    Configuration for the Voice Detection service.

    :param threshold: Speech probability threshold (0.0 to 1.0). Higher values require more confidence.
    :type threshold: float
    :param sampling_rate: Expected audio sample rate in Hz. Should match input audio.
    :type sampling_rate: int
    :param min_speech_duration_ms: Minimum duration in milliseconds to consider speech as valid.
    :type min_speech_duration_ms: float
    :param min_silence_duration_ms: Minimum duration in milliseconds of silence before considering speech ended.
    :type min_silence_duration_ms: float
    :param speech_pad_ms: Amount of padding to add to speech segments in milliseconds.
    :type speech_pad_ms: float
    :param message_frequency: Number of times per second to output messages regardless of state change (0 = only on state change).
    :type message_frequency: float
    """

    def __init__(
        self,
        threshold=0.5,
        sampling_rate=16000,
        min_speech_duration_ms=250,
        min_silence_duration_ms=100,
        speech_pad_ms=30,
        message_frequency=0,
    ):
        super(SICConfMessage, self).__init__()
        self.threshold = threshold
        self.sampling_rate = sampling_rate
        self.min_speech_duration_ms = min_speech_duration_ms
        self.min_silence_duration_ms = min_silence_duration_ms
        self.speech_pad_ms = speech_pad_ms
        self.message_frequency = message_frequency


class VoiceDetectionMessage(SICMessage):
    """
    Message indicating whether speech is detected or not.

    :param is_speaking: True if speech is currently detected, False otherwise.
    :type is_speaking: bool
    :param speech_proportion: The proportion of audio chunk that speech was detected in.
    :type speech_proportion: float
    """

    def __init__(self, is_speaking, speech_proportion=0.0):
        super().__init__()
        self.is_speaking = is_speaking
        self.speech_proportion = speech_proportion


class VoiceDetectionComponent(SICService):
    """
    SICService that detects voice activity in audio streams using Silero VAD.
    """

    COMPONENT_STARTUP_TIMEOUT = 10

    def __init__(self, *args, **kwargs):
        super(VoiceDetectionComponent, self).__init__(*args, **kwargs)

        # Configuration parameters (params are set by parent after super().__init__)
        self.threshold = self.params.threshold
        self.sampling_rate = self.params.sampling_rate
        self.min_speech_duration_ms = self.params.min_speech_duration_ms
        self.min_silence_duration_ms = self.params.min_silence_duration_ms
        self.speech_pad_ms = self.params.speech_pad_ms
        self.message_frequency = self.params.message_frequency

        # Load Silero VAD model
        self.logger.info("Loading Silero VAD model...")
        self.model, self.utils = torch.hub.load(
            repo_or_dir="snakers4/silero-vad",
            model="silero_vad",
            force_reload=False,
            onnx=False,
        )
        self.model.eval()  # Set to evaluation mode

        # Get VAD functions
        self.get_speech_timestamps = self.utils[0]
        self.save_audio = self.utils[1]
        self.read_audio = self.utils[2]
        self.collect_chunks = self.utils[3]

        # Initialize audio buffer for processing (rolling window)
        # Keep a buffer of recent audio for better detection
        self.audio_buffer = []
        self.buffer_lock = threading.Lock()
        self.buffer_duration_seconds = 1.0  # Keep 1 second of audio in buffer
        self.max_buffer_samples = int(self.sampling_rate * self.buffer_duration_seconds)

        # Speech state tracking
        self.current_speech_state = False  # True if currently speaking
        self.silence_start_time = None  # When silence was first detected (while currently speaking)
        self.silence_confirmation_delay = self.min_silence_duration_ms / 1000.0  # Convert to seconds
        
        # Message frequency tracking
        self.last_message_time = None  # Time when last message was sent
        self.message_interval = 1.0 / self.message_frequency if self.message_frequency > 0 else None

        # Minimum samples needed for processing (corresponds to window size)
        self.min_samples = int(self.sampling_rate * 0.064)  # 64ms window

        self.logger.info("Voice Detection Component initialized with Silero VAD")

    @staticmethod
    def get_inputs():
        return [AudioMessage]

    @staticmethod
    def get_output():
        return VoiceDetectionMessage

    @staticmethod
    def get_conf():
        return VoiceDetectionConf()

    def on_message(self, message):
        """
        Override to normalize timestamps from tuples to floats.
        Some devices send timestamps as tuples, but the framework expects floats.
        """
        # Normalize timestamp to float if it's a tuple
        if isinstance(message._timestamp, tuple):
            message._timestamp = float(message._timestamp[0])
        elif message._timestamp is not None:
            message._timestamp = float(message._timestamp)
        
        # Call parent's on_message to handle buffering
        super(VoiceDetectionComponent, self).on_message(message)

    def _bytes_to_tensor(self, waveform_bytes, sample_rate):
        """
        Convert audio bytes to torch tensor.

        :param waveform_bytes: Audio waveform as bytes (PCM 16-bit signed little endian).
        :type waveform_bytes: bytes
        :param sample_rate: Sample rate of the audio.
        :type sample_rate: int
        :return: Audio tensor and sample rate.
        :rtype: tuple
        """
        # Convert bytes to numpy array
        audio_array = np.frombuffer(waveform_bytes, dtype=np.int16).astype(np.float32)
        # Normalize to [-1, 1] range
        audio_array = audio_array / 32768.0

        # Convert to torch tensor
        audio_tensor = torch.from_numpy(audio_array)

        # Resample if needed
        if sample_rate != self.sampling_rate:
            resampler = torchaudio.transforms.Resample(sample_rate, self.sampling_rate)
            audio_tensor = resampler(audio_tensor.unsqueeze(0)).squeeze(0)

        return audio_tensor

    def _detect_speech(self, audio_tensor):
        """
        Detect speech in audio tensor using Silero VAD.

        :param audio_tensor: Audio tensor.
        :type audio_tensor: torch.Tensor
        :return: Tuple of (is_speaking, speech_proportion).
        :rtype: tuple
        """
        if len(audio_tensor) < self.min_samples:
            return False, 0.0

        try:
            # Silero VAD model expects tensor on CPU and returns speech probabilities
            # For real-time detection, we can use the model directly to get frame-level probabilities
            # and then aggregate them
            with torch.no_grad():
                # Get speech probabilities for the audio chunk
                # The model processes in windows, so we'll use a simpler approach
                speech_timestamps = self.get_speech_timestamps(
                    audio_tensor,
                    self.model,
                    threshold=self.threshold,
                    min_speech_duration_ms=self.min_speech_duration_ms,
                    min_silence_duration_ms=self.min_silence_duration_ms,
                    speech_pad_ms=self.speech_pad_ms,
                )

            # Calculate speech proportion (fraction of audio that is speech)
            total_samples = len(audio_tensor)
            speech_samples = 0
            
            # Handle different return formats from get_speech_timestamps
            # It can return: list of tuples, list of dicts, or list of lists
            for segment in speech_timestamps:
                if isinstance(segment, dict):
                    # Dictionary format: {'start': ..., 'end': ...}
                    start = float(segment.get('start', 0))
                    end = float(segment.get('end', 0))
                elif isinstance(segment, (list, tuple)):
                    # Tuple/list format: (start, end) or [start, end]
                    start = float(segment[0])
                    end = float(segment[1])
                else:
                    # Unknown format, skip
                    continue
                
                speech_samples += int(end - start)

            speech_proportion = min(1.0, speech_samples / total_samples) if total_samples > 0 else 0.0

            # Determine if currently speaking based on speech proportion
            # Use a threshold to avoid false positives
            is_speaking = speech_proportion > 0.1  # At least 10% of audio should be speech

            return is_speaking, speech_proportion
        except Exception as e:
            self.logger.error(f"Error in speech detection: {e}")
            import traceback
            self.logger.debug(traceback.format_exc())
            return False, 0.0

    def execute(self, inputs):
        """
        Process audio input and detect speech activity.

        :param inputs: Dictionary of input messages.
        :type inputs: SICMessageDictionary
        :return: VoiceDetectionMessage if speech state changed, None otherwise.
        :rtype: VoiceDetectionMessage | None
        """
        audio_message = inputs.get(AudioMessage)

        # Convert audio bytes to tensor
        try:
            audio_tensor = self._bytes_to_tensor(
                audio_message.waveform, audio_message.sample_rate
            )
        except Exception as e:
            self.logger.error(f"Error converting audio: {e}")
            return None

        # Add to buffer and maintain rolling window
        with self.buffer_lock:
            self.audio_buffer.extend(audio_tensor.numpy().tolist())
            
            # Keep only the most recent samples
            if len(self.audio_buffer) > self.max_buffer_samples:
                self.audio_buffer = self.audio_buffer[-self.max_buffer_samples:]

            # Check if we have enough data for processing
            if len(self.audio_buffer) < self.min_samples:
                return None

            # Convert buffer to tensor for processing
            buffer_tensor = torch.from_numpy(
                np.array(self.audio_buffer[-self.max_buffer_samples:], dtype=np.float32)
            )

        # Detect speech on the recent audio buffer
        is_speaking, speech_proportion = self._detect_speech(buffer_tensor)

        # Simple state change detection with confirmation delay
        current_time = time.time()
        state_changed = False

        if is_speaking:
            # Speech detected
            if not self.current_speech_state:
                # Transition from silence to speech - immediate (fast response)
                self.current_speech_state = True
                self.silence_start_time = None
                state_changed = True
            else:
                # Still speaking - clear any silence tracking
                self.silence_start_time = None
        else:
            # Silence detected
            if self.current_speech_state:
                # Currently marked as speaking, but silence detected - start tracking
                if self.silence_start_time is None:
                    self.silence_start_time = current_time
                
                # Check if silence has persisted long enough to confirm transition
                silence_duration = current_time - self.silence_start_time
                if silence_duration >= self.silence_confirmation_delay:
                    self.current_speech_state = False
                    self.silence_start_time = None
                    state_changed = True
            # else: already in silence state, no change needed

        # Determine if we should output a message
        should_output = False
        
        # Always output on state change
        if state_changed:
            should_output = True
            self.last_message_time = current_time
        # Also output periodically if message_frequency > 0
        elif self.message_frequency > 0 and self.message_interval is not None:
            if self.last_message_time is None:
                # First message
                should_output = True
                self.last_message_time = current_time
            else:
                # Check if enough time has passed for next periodic message
                time_since_last = current_time - self.last_message_time
                if time_since_last >= self.message_interval:
                    should_output = True
                    self.last_message_time = current_time

        # Output message if needed
        if should_output:
            return VoiceDetectionMessage(
                is_speaking=self.current_speech_state,
                speech_proportion=speech_proportion,
            )

        return None

    def stop(self):
        """
        Stop the VoiceDetectionComponent.
        """
        self._stopped.set()
        super(VoiceDetectionComponent, self).stop()


class VoiceDetection(SICConnector):
    """
    Connector for the Voice Detection Component.
    """
    component_class = VoiceDetectionComponent


def main():
    """
    Run a ComponentManager that can start the Voice Detection Component.
    """
    SICComponentManager([VoiceDetectionComponent], name="VoiceDetection")


if __name__ == "__main__":
    main()
