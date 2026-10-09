"""
localvqe_messages.py

Message and configuration types for the LocalVQE service.
"""

from sic_framework.core.message_python2 import (
    AudioMessage,
    SICConfMessage,
    SICRequest,
)


class RefAudioMessage(AudioMessage):
    """
    Far-end reference audio (int16 PCM, 16 kHz mono): a distinct type so both
    streams can share one connector without colliding in the input buffers.
    """


class LocalVQEResetRequest(SICRequest):
    """Reset the LocalVQE streaming state and drop buffered samples."""


class LocalVQEConf(SICConfMessage):
    """
    LocalVQE service configuration. model_path None resolves $LOCALVQE_MODEL,
    then ~/.cache/sic/models/localvqe-v1.3-4.8M-f32.gguf. use_ref=True adds
    the RefAudioMessage far-end stream for echo cancellation (both streams
    must then keep flowing; a reference lagging max_ref_lag_seconds is
    zero-filled). frontend_path is for the GTCRN model line only.
    """

    def __init__(
        self,
        model_path=None,
        use_ref=False,
        threads=None,
        backend=None,
        device=None,
        frontend_path=None,
        noise_gate_dbfs=None,
        max_ref_lag_seconds=1.0,
        lib_path=None,
    ):
        SICConfMessage.__init__(self)
        self.model_path = model_path
        self.use_ref = use_ref
        self.threads = threads
        self.backend = backend
        self.device = device
        self.frontend_path = frontend_path
        self.noise_gate_dbfs = noise_gate_dbfs
        self.max_ref_lag_seconds = max_ref_lag_seconds
        self.lib_path = lib_path
