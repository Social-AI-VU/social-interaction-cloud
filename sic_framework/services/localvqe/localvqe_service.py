"""
localvqe_service.py

SIC service for LocalVQE's GGML voice quality enhancement (AEC + noise
suppression + dereverb) on 16 kHz mono audio. Run with `run-localvqe`.
"""

import numpy as np

from sic_framework import SICComponentManager
from sic_framework.core.connector import SICConnector
from sic_framework.core.message_python2 import AudioMessage, SICSuccessMessage
from sic_framework.core.service_python2 import SICService
from sic_framework.services.localvqe.localvqe_binding import (
    LocalVQE as LocalVQEBinding,
    f32_to_pcm16,
    pcm16_to_f32,
)
from sic_framework.services.localvqe.localvqe_messages import (
    LocalVQEConf,
    LocalVQEResetRequest,
    RefAudioMessage,
)


class LocalVQEService(SICService):
    """Voice quality enhancement service (AEC + NS + dereverb) backed by LocalVQE's GGML engine."""

    COMPONENT_STARTUP_TIMEOUT = 60

    def __init__(self, *args, **kwargs):
        super(LocalVQEService, self).__init__(*args, **kwargs)

        conf = self.params
        self.vqe = LocalVQEBinding(
            model_path=conf.model_path,
            threads=conf.threads,
            backend=conf.backend,
            device=conf.device,
            frontend_path=conf.frontend_path,
            noise_gate_dbfs=conf.noise_gate_dbfs,
            lib_path=conf.lib_path,
        )
        self._hop_bytes = self.vqe.hop_length * 2  # int16 PCM
        self._mic_buf = bytearray()
        self._ref_buf = bytearray()
        self._warned_rate = False
        self._warned_ref_lag = False
        self._warned_ref_ignored = False

        self.logger.info(
            "LocalVQE ready: model={} sample_rate={} hop={} use_ref={} threads={} backend={}".format(
                self.vqe.model_path,
                self.vqe.sample_rate,
                self.vqe.hop_length,
                conf.use_ref,
                conf.threads or "auto",
                conf.backend or "CPU",
            )
        )

    # Instance method (the framework calls self.get_inputs()): the aligner needs
    # every declared input to flow, so the reference is declared only with use_ref.
    def get_inputs(self):
        if self.params.use_ref:
            return [AudioMessage, RefAudioMessage]
        return [AudioMessage]

    @staticmethod
    def get_output():
        return AudioMessage

    @staticmethod
    def get_conf():
        return LocalVQEConf()

    def on_message(self, message):
        # Redis TIME stamps are (sec, usec) tuples; the aligner subtracts
        # timestamps, so flatten to float seconds before buffering.
        if isinstance(message._timestamp, (tuple, list)):
            message._timestamp = message._timestamp[0] + message._timestamp[1] / 1e6
        # Without use_ref a stray RefAudioMessage (an AudioMessage subclass)
        # would open an extra input buffer and stall alignment - drop it.
        if not self.params.use_ref and message.get_message_name() == RefAudioMessage.get_message_name():
            if not self._warned_ref_ignored:
                self._warned_ref_ignored = True
                self.logger.warning(
                    "Ignoring RefAudioMessage stream: the service was started with "
                    "use_ref=False (set LocalVQEConf(use_ref=True) for echo cancellation)"
                )
            return
        super(LocalVQEService, self).on_message(message)

    # Pair oldest-first: audio devices can deliver identical-timestamp doubles,
    # which the newest-first default swaps or strands - FIFO keeps stream order.
    def _find_aligned_message(self, buffer, reference_timestamp):
        for message in reversed(buffer):
            if abs(message._timestamp - reference_timestamp) <= self.MAX_TIMESTAMP_DIFF_SECONDS:
                return message
        return None

    # Consume by identity: SICMessage.__eq__ is type-equality, so deque.remove
    # would delete the newest same-type message instead of the one chosen above.
    def _consume_messages(self, aligned_messages):
        for buffer, message in aligned_messages:
            for i, queued in enumerate(buffer):
                if queued is message:
                    del buffer[i]
                    break

    def on_request(self, request):
        if isinstance(request, LocalVQEResetRequest):
            self.vqe.reset()
            del self._mic_buf[:]
            del self._ref_buf[:]
            self.logger.info("LocalVQE streaming state reset")
            return SICSuccessMessage()
        raise NotImplementedError("Unknown request type {}".format(type(request)))

    def _check_message(self, message, name):
        """Validate one input message; returns its PCM bytes (or None to skip)."""
        if message.sample_rate != self.vqe.sample_rate:
            if not self._warned_rate:
                self._warned_rate = True
                self.logger.error(
                    "{} stream is {} Hz but LocalVQE requires {} Hz mono int16 PCM. "
                    "Resample at the source (e.g. MicrophoneConf(sample_rate=16000)); "
                    "dropping audio.".format(name, message.sample_rate, self.vqe.sample_rate)
                )
            return None
        waveform = bytes(message.waveform)
        if len(waveform) % 2:
            self.logger.warning("{} chunk has odd byte length; dropping last byte".format(name))
            waveform = waveform[:-1]
        return waveform

    def execute(self, inputs):
        mic = self._check_message(inputs.get(AudioMessage), "mic")
        if mic is None:
            return None
        self._mic_buf.extend(mic)

        if self.params.use_ref:
            ref = self._check_message(inputs.get(RefAudioMessage), "ref")
            if ref is not None:
                self._ref_buf.extend(ref)
            # Zero-fill a lagging reference so enhancement never stalls.
            max_lag_bytes = int(self.params.max_ref_lag_seconds * self.vqe.sample_rate) * 2
            lag = len(self._mic_buf) - len(self._ref_buf)
            if lag > max_lag_bytes:
                if not self._warned_ref_lag:
                    self._warned_ref_lag = True
                    self.logger.warning(
                        "Reference stream lags the mic stream by more than {:.2f}s; "
                        "zero-filling the reference (echo cancellation degrades "
                        "until it catches up)".format(self.params.max_ref_lag_seconds)
                    )
                self._ref_buf.extend(b"\x00" * lag)
        else:
            self._ref_buf.extend(b"\x00" * len(mic))

        n_hops = min(len(self._mic_buf), len(self._ref_buf)) // self._hop_bytes
        if n_hops == 0:
            return None

        take = n_hops * self._hop_bytes
        mic_f = pcm16_to_f32(bytes(self._mic_buf[:take]))
        ref_f = pcm16_to_f32(bytes(self._ref_buf[:take]))
        del self._mic_buf[:take]
        del self._ref_buf[:take]

        hop = self.vqe.hop_length
        out = np.empty(n_hops * hop, dtype=np.float32)
        for i in range(0, n_hops * hop, hop):
            out[i:i + hop] = self.vqe.process_frame(mic_f[i:i + hop], ref_f[i:i + hop])

        return AudioMessage(
            waveform=f32_to_pcm16(out),
            sample_rate=self.vqe.sample_rate,
            is_stream=True,
        )

    def _cleanup(self):
        try:
            self.vqe.close()
        except Exception as e:
            self.logger.warning("Error closing LocalVQE context: {}".format(e))


class SICLocalVQE(SICConnector):
    """Connector for the LocalVQE voice quality enhancement service."""

    component_class = LocalVQEService
    component_group = "LocalVQE"


def main():
    """Run a ComponentManager that can start the LocalVQE service."""
    SICComponentManager([LocalVQEService], component_group="LocalVQE")


if __name__ == "__main__":
    main()
