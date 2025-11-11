import queue
import threading
from datetime import datetime

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import torch
import torch.amp
from huggingface_hub import get_token as get_hf_token

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

try:
    from nemo.collections.asr.models import SortformerEncLabelModel
    from nemo.collections.asr.parts.utils.speaker_utils import (
        generate_diarization_output_lines,
    )
    from nemo.collections.asr.parts.utils.vad_utils import (
        load_postprocessing_from_yaml,
        ts_vad_post_processing,
    )
except ImportError:
    raise SystemExit(
        """Please use `pip install "git+https://github.com/NVIDIA/NeMo.git@main#egg=nemo_toolkit[asr]"` to use the Sortformer diarization"""
    )


class STMSortformerConf(SICConfMessage):
    """
    Ultra low latency configuration for the Streaming Sortformer diarization component.
    For other configurations, see:
    https://huggingface.co/nvidia/diar_streaming_sortformer_4spk-v2#setting-up-streaming-configuration

    :param local_model: Path to the local NeMo diarization model checkpoint (.nemo file)
    :type local_model: str
    :param model_yaml: Path to the YAML configuration file for diarization post-processing
    :type model_yaml: str
    :param CHUNK_SIZE: Base chunk length (in frames) used by the streaming Sortformer
    :type CHUNK_SIZE: int
    :param RIGHT_CONTEXT: Number of chunks of future context used during streaming inference
    :type RIGHT_CONTEXT: int
    :param FIFO_SIZE: Size of the internal prediction FIFO buffer in frames
    :type FIFO_SIZE: int
    :param UPDATE_PERIOD: Interval (in frames) at which the speaker cache is updated
    :type UPDATE_PERIOD: int
    :param SPEAKER_CACHE_SIZE: Number of frames kept in the speaker cache to ensure continuity
    :type SPEAKER_CACHE_SIZE: int
    """

    def __init__(
        self,
        local_model="./data/diar_streaming_sortformer_4spk-v2.nemo",
        model_yaml="./data/diar_streaming_sortformer_4spk-v2_dihard3-dev.yaml",
        CHUNK_SIZE=3,
        RIGHT_CONTEXT=1,
        FIFO_SIZE=188,
        UPDATE_PERIOD=144,
        SPEAKER_CACHE_SIZE=188,
    ):
        super(SICConfMessage, self).__init__()
        self.local_model = local_model
        self.model_yaml = model_yaml
        self.CHUNK_SIZE = CHUNK_SIZE
        self.RIGHT_CONTEXT = RIGHT_CONTEXT
        self.FIFO_SIZE = FIFO_SIZE
        self.UPDATE_PERIOD = UPDATE_PERIOD
        self.SPEAKER_CACHE_SIZE = SPEAKER_CACHE_SIZE


class GetDiarizationRequest(SICRequest):
    """
    Request for retrieving diarization output from the component.
    """

    def __init__(self):
        super().__init__()


class DiarizationResult(SICMessage):
    """
    Message containing diarization results produced by the model.

    :param predictions: Tensor of speaker activity probabilities over time
    :type predictions: torch.Tensor
    :param speaker_timestamps: List of lists with (start_time, end_time) pairs per speaker
    :type speaker_timestamps: list[list[list[float]]]
    """

    def __init__(self, predictions, speaker_timestamps):
        self.predictions = predictions
        self.speaker_timestamps = speaker_timestamps


class STMSortformerComponent(SICComponent):
    """
    This SICComponent:
        - Takes streaming audio as input from any device
        - Performs online feature extraction and streaming inference
        - Maintains internal state for low-latency speaker diarization
        - Exposes diarization results via SIC request/response messages
    """

    COMPONENT_STARTUP_TIMEOUT = 10

    def __init__(self, *args, **kwargs):
        super(STMSortformerComponent, self).__init__(*args, **kwargs)
        self.stream_start_timestamp_unix = None
        # Load Streaming Sortformer model from HF or locally
        self._load_model()
        # Streaming parameters corresponding to 0.32s latency setup.
        self._configure_model()
        # Speaker probabilities post_processing
        self.post_processing_params = load_postprocessing_from_yaml(
            self.params.model_yaml
        )
        self.unit_10ms_frame_count = int(
            self.diar_model._cfg.encoder.subsampling_factor
        )
        # Init models' state and batching params
        self._init_streaming_state()
        self._configure_batching_params()
        # Start thread
        t = threading.Thread(target=self._streaming_diarization_thd)
        t.start()

    def _load_model(self):
        hf_token = get_hf_token()
        if hf_token and hf_token.startswith("hf_"):
            self.diar_model = SortformerEncLabelModel.from_pretrained(
                "nvidia/diar_streaming_sortformer_4spk-v2"
            )
        else:
            self.diar_model = SortformerEncLabelModel.restore_from(
                restore_path=self.params.local_model,
                map_location=torch.device("cuda"),
                strict=False,
            )

    def _configure_model(self):
        self.diar_model.eval()
        if torch.cuda.is_available():
            self.diar_model.to(torch.device("cuda"))
        self.autocast_enabled = self.diar_model.device.type == "cuda"
        self.device = self.diar_model.device
        self.diar_model.sortformer_modules.chunk_len = self.params.CHUNK_SIZE
        self.diar_model.sortformer_modules.spkcache_len = self.params.SPEAKER_CACHE_SIZE
        self.diar_model.sortformer_modules.chunk_right_context = (
            self.params.RIGHT_CONTEXT
        )
        self.diar_model.sortformer_modules.fifo_len = self.params.FIFO_SIZE
        self.diar_model.sortformer_modules.spkcache_update_period = (
            self.params.UPDATE_PERIOD
        )
        self.diar_model.sortformer_modules.log = False
        self.diar_model.sortformer_modules._check_streaming_parameters()

    def _init_streaming_state(self):
        self.batch_size = 1
        self.processed_signal_offset = torch.zeros(
            (self.batch_size,), dtype=torch.long, device=self.device
        )
        self.streaming_state = self.diar_model.sortformer_modules.init_streaming_state(
            batch_size=self.batch_size, async_streaming=True, device=self.device
        )
        self.total_preds = torch.zeros(
            (self.batch_size, 0, self.diar_model.sortformer_modules.n_spk),
            device=self.device,
        )

    def _configure_batching_params(self):
        self.sr = 16000
        self.hop_s = float(self.diar_model.preprocessor._cfg.window_stride)
        self.hop = int(round(self.sr * self.hop_s))
        self.chunk_len = self.diar_model.sortformer_modules.chunk_len
        self.subfac = self.diar_model.sortformer_modules.subsampling_factor
        self.base_frames = self.chunk_len * self.subfac
        self.chunk_size = self.base_frames * self.hop
        self.L_off = 8
        self.R_off = 8
        self.ctx_left = self.L_off * self.hop
        self.ctx_right = self.R_off * self.hop
        self.stream_queue = queue.Queue()
        self.results_queue = queue.Queue()
        self.stream_buffer = np.zeros(0, dtype=np.float32)
        self.buffer_offset = 0
        self.processed_until = 0

    def _melspectogram_preprocessing(self, raw_with_ctx):
        """
        Convert raw waveform audio (with context) into model-ready features.

        Applies the model preprocessor to compute log-mel spectrograms and crops
        the output to valid (unpadded) frames.

        :param raw_with_ctx: 1D NumPy array of float32 containing waveform samples
                             including left/right context
        :type raw_with_ctx: numpy.ndarray
        :return: Tuple of (processed_signal, processed_signal_length)
                 where processed_signal has shape (1, T, F)
        :rtype: tuple[torch.Tensor, torch.Tensor]
        """
        audio_signal = torch.tensor(
            raw_with_ctx, dtype=torch.float32, device=self.device
        ).unsqueeze(0)
        audio_signal_length = torch.tensor([audio_signal.shape[1]], device=self.device)
        processed_signal, processed_signal_length = self.diar_model.preprocessor(
            input_signal=audio_signal, length=audio_signal_length
        )
        # (B, F, T) -> (B, T, F)
        processed_signal = processed_signal.transpose(1, 2)
        # CROP to the valid (unpadded) frames
        T_valid = int(processed_signal_length.item())
        processed_signal = processed_signal[:, :T_valid, :]
        return processed_signal, processed_signal_length

    def _get_speaker_timestamps(self, preds, base_time_unix: float = 0.0):
        """
        Convert per-frame speaker probabilities into timestamped speech segments.

        Runs VAD-style post-processing for each speaker to obtain contiguous speech
        regions, then offsets them by a base UNIX timestamp.

        :param preds: Tensor of shape (1, T, S) containing speaker probabilities
        :type preds: torch.Tensor
        :param base_time_unix: UNIX timestamp (seconds) corresponding to frame 0
        :type base_time_unix: float
        :return: List of per-speaker timestamp intervals
                 [[(start, end), ...] for each speaker]
        :rtype: list[list[list[float]]]
        """
        probs = preds[0].detach().cpu()
        num_speakers = probs.shape[1]

        speaker_timestamps = []
        for spk_id in range(num_speakers):
            spk_probs = probs[:, spk_id]

            ts_mat = ts_vad_post_processing(
                spk_probs,
                cfg_vad_params=self.post_processing_params,
                unit_10ms_frame_count=self.unit_10ms_frame_count,
                bypass_postprocessing=False,
            )

            ts_list = [
                [base_time_unix + float(stt), base_time_unix + float(end)]
                for (stt, end) in ts_mat.tolist()
            ]
            speaker_timestamps.append(ts_list)
        return speaker_timestamps

    def _streaming_diarization_thd(self):
        while True:
            stream_chunk = self.stream_queue.get()
            if stream_chunk is None or stream_chunk.size == 0:
                continue
            else:
                self.stream_buffer = np.concatenate([self.stream_buffer, stream_chunk])

            base_start_global = self.processed_until
            base_end_global = base_start_global + self.chunk_size

            # Check if we have enough samples for base chunk in *global* coordinates
            if base_end_global > self.buffer_offset + len(self.stream_buffer):
                continue

            # Require full right context
            needed_end_global = base_end_global + self.ctx_right
            if needed_end_global > (self.buffer_offset + len(self.stream_buffer)):
                continue

            # Global start/end with context (same logic as offline)
            if base_start_global == 0:
                start_global = 0
            else:
                start_global = max(0, base_start_global - self.ctx_left)

            end_global = min(
                self.buffer_offset + len(self.stream_buffer), needed_end_global
            )

            # Map global indices to local indices into stream_buffer
            local_start = start_global - self.buffer_offset
            local_end = end_global - self.buffer_offset

            raw_with_ctx = self.stream_buffer[local_start:local_end]
            processed_signal, processed_signal_length = (
                self._melspectogram_preprocessing(raw_with_ctx)
            )

            with (
                torch.inference_mode(),
                torch.amp.autocast(self.device.type, enabled=self.autocast_enabled),
            ):
                self.streaming_state, self.total_preds = (
                    self.diar_model.forward_streaming_step(
                        processed_signal=processed_signal,
                        processed_signal_length=processed_signal_length,
                        streaming_state=self.streaming_state,
                        total_preds=self.total_preds,
                        left_offset=(0 if base_start_global == 0 else self.L_off),
                        right_offset=self.R_off,
                    )
                )
                speaker_timestamps = self._get_speaker_timestamps(
                    self.total_preds, self.stream_start_timestamp_unix
                )
                self.results_queue.put((self.total_preds, speaker_timestamps))

            # Move to next base chunk
            self.processed_until = base_end_global

            # Trim old samples we don't need anymore
            next_base_start_global = self.processed_until
            min_needed_global = max(0, next_base_start_global - self.ctx_left)
            safe_drop = min(
                max(0, min_needed_global - self.buffer_offset), len(self.stream_buffer)
            )
            if safe_drop > 0:
                self.stream_buffer = self.stream_buffer[safe_drop:]
                self.buffer_offset += safe_drop

    @staticmethod
    def get_inputs():
        return [AudioMessage, GetDiarizationRequest]

    @staticmethod
    def get_output():
        return DiarizationResult

    @staticmethod
    def get_conf():
        return STMSortformerConf()

    def on_message(self, message):
        """
        Handle incoming audio messages.

        :param message: Incoming audio message containing waveform and timestamp
        :type message: AudioMessage
        """
        if not isinstance(message, AudioMessage):
            self.logger.error(f"Invalid message type: {type(message)}")
            return
        self.logger.debug(message.sample_rate)
        if self.stream_start_timestamp_unix is None:
            self.stream_start_timestamp_unix = float(message._timestamp[0])
        pcm_int16 = np.frombuffer(message.waveform, dtype=np.int16)
        pcm_flt32 = pcm_int16.astype(np.float32) / 32768.0
        self.stream_queue.put(pcm_flt32)

    def on_request(self, request):
        """
        Handle incoming diarization requests.

        :param request: Request message for diarization results
        :type request: GetDiarizationRequest
        :return: DiarizationResult object with predictions and timestamps
        :rtype: DiarizationResult
        :raises NotImplementedError: If the request type is unsupported
        """
        if is_sic_instance(request, GetDiarizationRequest):
            preds, speaker_timestamps = self.results_queue.get()
            return DiarizationResult(
                predictions=preds, speaker_timestamps=speaker_timestamps
            )
        else:
            raise NotImplementedError("Unknown request type {}".format(type(request)))


class STMSortformerUtils:
    """
    Utility helpers for inspecting and visualizing streaming diarization output.
    """

    def show_diar_df(self, speaker_timestamps, gap_threshold=0.75):
        """
        Convert diarization timestamps into a formatted pandas DataFrame.

        :param speaker_timestamps: List of per-speaker timestamp intervals
                                   [[[start, end], ...], ...]
        :type speaker_timestamps: list[list[list[float]]]
        :param gap_threshold: Maximum allowed gap (in seconds) between segments to merge
        :type gap_threshold: float
        :return: DataFrame with columns ["Start Time", "End Time", "Speaker"],
                 where times are formatted as HH:MM:SS.mmm
        :rtype: pandas.DataFrame
        """
        rows = []
        for spk_idx, segments in enumerate(speaker_timestamps):
            for start, end in segments:
                rows.append(
                    {
                        "Start Time": start,
                        "End Time": end,
                        "Speaker": f"Speaker {spk_idx + 1}",
                    }
                )

        if not rows:
            return pd.DataFrame(columns=["Start Time", "End Time", "Speaker"])

        df = pd.DataFrame(rows).sort_values("Start Time").reset_index(drop=True)

        # Merge consecutive segments for same speaker
        merged, current = [], df.iloc[0].to_dict()
        for _, row in df.iloc[1:].iterrows():
            if (
                row["Speaker"] == current["Speaker"]
                and row["Start Time"] - current["End Time"] <= gap_threshold
            ):
                current["End Time"] = row["End Time"]
            else:
                merged.append(current)
                current = row.to_dict()
        merged.append(current)

        df = pd.DataFrame(merged)

        # Convert to HH:MM:SS.mmm clock time
        fmt = (
            lambda ts: datetime.fromtimestamp(ts).strftime("%H:%M:%S.")
            + f"{int(datetime.fromtimestamp(ts).microsecond / 1000):03d}"
        )
        df["Start Time"] = df["Start Time"].apply(fmt)
        df["End Time"] = df["End Time"].apply(fmt)

        return df[["Start Time", "End Time", "Speaker"]]

    def rt_plot_diarout(self, preds, frame_ms=80, window_sec=5.20):
        """
        Plot a real-time rolling window of diarization probabilities as a heatmap.

        :param preds: Tensor containing diarization predictions with shape (T, S) or (1, T, S)
        :type preds: torch.Tensor
        :param frame_ms: Duration of each frame in milliseconds
        :type frame_ms: float
        :param window_sec: Duration of the rolling window to display in seconds
        :type window_sec: float
        :raises ValueError: If `preds` does not have 2 or 3 dimensions
        """
        if preds.ndim == 3:
            preds = preds[0]
        elif preds.ndim != 2:
            raise ValueError(
                f"Expected preds to have 2 or 3 dims, got shape {preds.shape}"
            )

        preds_np = preds.detach().cpu().numpy()
        T, S = preds_np.shape

        frame_sec = frame_ms / 1000.0
        window_frames = int(round(window_sec / frame_sec))

        # Build window: last window_frames frames, left-pad if needed
        if T >= window_frames:
            window_np = preds_np[-window_frames:, :]
            start_label = T - window_frames
            x_labels = [start_label + j for j in range(window_frames)]
        else:
            pad_len = window_frames - T
            pad = np.zeros((pad_len, S), dtype=preds_np.dtype)
            window_np = np.concatenate([pad, preds_np], axis=0)
            x_labels = [j - pad_len for j in range(window_frames)]

        preds_mat = window_np.transpose()
        self._plot_diar_matrix(
            preds_mat,
            title=f"Predictions (last {window_sec:.2f} s)",
            frame_label=f"{frame_ms} ms Frames (rolling window)",
        )

    def save_final_diarout(self, preds):
        """
        Save the final diarization probability matrix as an image file.

        :param preds: Tensor containing full diarization predictions with shape (T, S)
        :type preds: torch.Tensor
        """
        preds_mat = preds.cpu().numpy().transpose()
        self._plot_diar_matrix(
            preds_mat,
            title="Predictions",
            frame_label="80 ms Frames",
            save_path="plot.png",
        )

    def _plot_diar_matrix(self, preds_mat, title, frame_label, save_path=None):
        """
        Internal helper to plot a diarization probability matrix as a heatmap.

        :param preds_mat: 2D array of shape (num_speakers, num_frames) with probabilities
        :type preds_mat: numpy.ndarray
        :param title: Title text for the plot
        :type title: str
        :param frame_label: Label for the x-axis indicating frame/time units
        :type frame_label: str
        :param save_path: Optional path to save the plot image; if None, the plot is shown
        :type save_path: str | None
        """
        yticklabels = [f"spk{i}" for i in range(preds_mat.shape[0])]
        yticks = np.arange(len(yticklabels))
        cmap_str, grid_color_p = "viridis", "gray"
        LW, FS = 0.4, 18

        fig, axs = plt.subplots(1, 1, figsize=(30, 3))
        axs.imshow(preds_mat, cmap=cmap_str, interpolation="nearest")
        axs.set_title(title, fontsize=FS)
        axs.set_xticks(np.arange(-0.5, preds_mat.shape[1], 1), minor=True)
        axs.set_yticks(yticks)
        axs.set_yticklabels(yticklabels)
        axs.set_xlabel(frame_label, fontsize=FS)
        axs.grid(which="minor", color=grid_color_p, linestyle="-", linewidth=LW)

        if save_path:
            plt.savefig(save_path, dpi=300)
        else:
            plt.show()


class STMSortformer(SICConnector):
    component_class = STMSortformerComponent


if __name__ == "__main__":
    SICComponentManager([STMSortformerComponent], name="Streaming Sortformer")
