import wave
import numpy as np

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

INT16_MAX = np.iinfo(np.int16).max
INT16_MIN = np.iinfo(np.int16).min


class AudioSourceRequest(SICRequest):

    def __init__(
        self,
        frame: int,
        kind: str,
        key: str,
        path: str | None = None,
        volume: float = 1.0,
        fade: float = 0.0
    ):
        super().__init__()
        self.frame = frame
        self.kind = kind
        self.key = key
        self.path = path
        self.volume = volume
        self.fade = fade


class AudioSource:

    def __init__(self, pcm_data: np.ndarray, sample_rate: int, volume: float = 1.0):
        assert pcm_data.dtype == np.int16
        assert pcm_data.ndim == 2

        self.data = pcm_data
        self.position = 0
        self.sample_rate = sample_rate

        self.volume = float(volume)
        self._target_volume = float(volume)
        self._fade_frames_remaining = 0
        self._pause_after_fade = False
        self.paused = False

    @property
    def done(self) -> bool:
        return self.position >= self.data.shape[0]

    @property
    def is_paused(self) -> bool:
        return self.paused

    def pause(self) -> None:
        self.paused = True
        self._pause_after_fade = False
        self._cancel_fade()

    def resume(self) -> None:
        self.paused = False
        self._pause_after_fade = False

    def pause_with_fade(self, duration_sec: float) -> None:
        if duration_sec <= 0:
            self.pause()
            return
        self._pause_after_fade = True
        self._start_fade(target_volume=0.0, duration_sec=duration_sec)

    def resume_with_fade(self, duration_sec: float, final_volume: float = 1.0) -> None:
        if duration_sec <= 0:
            self.paused = False
            self.set_volume(final_volume)
            return

        self.paused = False
        self._pause_after_fade = False
        self.volume = 0.0
        self._start_fade(target_volume=final_volume, duration_sec=duration_sec)

    def set_volume(self, volume: float) -> None:
        vol = float(volume)
        self.volume = vol
        self._target_volume = vol
        self._cancel_fade()
        self._pause_after_fade = False

    def fade_to(self, target_volume: float, duration_sec: float) -> None:
        self._pause_after_fade = False
        self._start_fade(target_volume=target_volume, duration_sec=duration_sec)

    def fade_in(self, duration_sec: float, final_volume: float = 1.0) -> None:
        self.paused = False
        self._pause_after_fade = False
        self.volume = 0.0
        self._start_fade(target_volume=final_volume, duration_sec=duration_sec)

    def fade_out(self, duration_sec: float) -> None:
        self._pause_after_fade = False
        self._start_fade(target_volume=0.0, duration_sec=duration_sec)

    def _cancel_fade(self) -> None:
        self._fade_frames_remaining = 0
        self._target_volume = self.volume

    def _start_fade(self, target_volume: float, duration_sec: float) -> None:
        if duration_sec <= 0:
            self.set_volume(target_volume)
            return

        self._target_volume = float(target_volume)
        self._fade_frames_remaining = max(1, int(duration_sec * self.sample_rate))

    def _silent_chunk(self, n_frames: int) -> np.ndarray:
        channels = self.data.shape[1]
        return np.zeros((n_frames, channels), dtype=np.int32)

    def _get_volume_envelope(self, n_frames: int) -> np.ndarray:
        if self._fade_frames_remaining <= 0:
            return np.full(n_frames, self.volume, dtype=np.float32)

        env = np.empty(n_frames, dtype=np.float32)
        vol = self.volume
        tgt = self._target_volume
        remaining = self._fade_frames_remaining

        for i in range(n_frames):
            if remaining > 0:
                step = (tgt - vol) / remaining
                vol += step
                remaining -= 1
            env[i] = vol

        self.volume = vol
        self._fade_frames_remaining = remaining

        if remaining <= 0:
            self.volume = self._target_volume
            if self._pause_after_fade and self.volume <= 1e-4:
                self.paused = True
                self._pause_after_fade = False

        return env

    def get_chunk_with_envelope(self, n_frames: int) -> np.ndarray:
        if self.paused or self.done:
            return self._silent_chunk(n_frames)

        channels = self.data.shape[1]

        end = min(self.position + n_frames, self.data.shape[0])
        raw_chunk = self.data[self.position:end].astype(np.float32)
        self.position = end

        n_got = raw_chunk.shape[0]
        if n_got < n_frames:
            pad = np.zeros((n_frames - n_got, channels), dtype=np.float32)
            raw_chunk = np.vstack([raw_chunk, pad])

        env = self._get_volume_envelope(n_frames)  # (n_frames,)
        raw_chunk *= env[:, None]

        return raw_chunk.astype(np.int32)


class AudioMixerConf(SICConfMessage):

    def __init__(self, sample_rate: int, channels: int, chunk_size: int):
        super(SICConfMessage, self).__init__()
        self.sample_rate = sample_rate
        self.channels = channels
        self.chunk_size = chunk_size

class AudioMixerRequest(SICRequest):

    def __init__(self, kind: str, **kwargs):
        super().__init__()
        self.kind = kind
        self.kwargs = kwargs


class AudioMixerComponent(SICComponent):

    def __init__(self, *args, **kwargs):
        super(AudioMixerComponent, self).__init__(*args, **kwargs)
        assert self.params.channels in (1, 2)
        assert 4096 <= self.params.chunk_size <= 16384
        self.sample_rate = self.params.sample_rate
        self.channels = self.params.channels
        self.chunk_size = self.params.chunk_size
        self.sources: list[AudioSource] = []
        self._sources_by_key: dict[str, AudioSource] = {}
        self._clips: dict[str, np.ndarray] = {}

    def add_source(self, pcm_data: np.ndarray, volume: float = 1.0) -> AudioSource:
        if pcm_data.ndim == 1:
            pcm_data = pcm_data[:, None] 

        assert pcm_data.dtype == np.int16
        assert pcm_data.shape[1] == self.channels

        src = AudioSource(pcm_data, sample_rate=self.sample_rate, volume=volume)
        self.sources.append(src)
        return src

    def stop_source(self, src: AudioSource) -> None:
        if src in self.sources:
            self.sources.remove(src)

    def stop_all(self) -> None:
        self.sources.clear()

    def next_chunk(self) -> bytes:
        mix = np.zeros((self.chunk_size, self.channels), dtype=np.int32)
        alive: list[AudioSource] = []

        for src in self.sources:
            if src.done:
                continue

            chunk = src.get_chunk_with_envelope(self.chunk_size)
            mix += chunk

            if not src.done:
                alive.append(src)

        self.sources = alive

        np.clip(mix, INT16_MIN, INT16_MAX, out=mix)
        out = mix.astype(np.int16)
        return out.tobytes()

    def _resample_1d(self, x: np.ndarray, src_sr: int, dst_sr: int) -> np.ndarray:
        if src_sr == dst_sr:
            return x.astype(np.float32, copy=False)

        src_len = x.shape[0]
        duration = src_len / src_sr
        dst_len = int(round(duration * dst_sr))

        if dst_len <= 1 or src_len <= 1:
            return np.zeros(dst_len, dtype=np.float32)

        t_src = np.linspace(0, src_len - 1, num=src_len, endpoint=True)
        t_dst = np.linspace(0, src_len - 1, num=dst_len, endpoint=True)

        y = np.interp(t_dst, t_src, x.astype(np.float32))
        return y.astype(np.float32)


    def _resample_stereo(self, data: np.ndarray, src_sr: int, dst_sr: int) -> np.ndarray:
        if src_sr == dst_sr:
            return data

        n_channels = data.shape[1]
        out_channels = []
        for c in range(n_channels):
            ch = data[:, c].astype(np.float32)
            ch_resampled = self._resample_1d(ch, src_sr, dst_sr)
            out_channels.append(ch_resampled)

        out = np.stack(out_channels, axis=1)
        return out


    def _convert_channels(self, data: np.ndarray, src_channels: int, dst_channels: int) -> np.ndarray:
        if src_channels == dst_channels:
            return data

        if src_channels == 1 and dst_channels == 2:
            return np.repeat(data, 2, axis=1)

        if src_channels == 2 and dst_channels == 1:
            mono = data.mean(axis=1, keepdims=True)
            return mono

        raise ValueError(f"Unsupported channel conversion {src_channels} -> {dst_channels}")

    def load_wav_int16(self, path: str, target_sample_rate: int, target_channels: int):
        with wave.open(path, "rb") as wf:
            src_channels = wf.getnchannels()
            src_sample_rate = wf.getframerate()
            n_frames = wf.getnframes()

            raw = wf.readframes(n_frames)

        data = np.frombuffer(raw, dtype=np.int16)

        if src_channels > 1:
            data = data.reshape(-1, src_channels)
        else:
            data = data.reshape(-1, 1)

        data = self._convert_channels(data, src_channels, target_channels)

        data_f = data.astype(np.float32)
        data_resampled = self._resample_stereo(data_f, src_sample_rate, target_sample_rate)

        np.clip(data_resampled, INT16_MIN, INT16_MAX, out=data_resampled)
        data_int16 = data_resampled.astype(np.int16)

        return target_sample_rate, target_channels, data_int16

    def _handle_src_request(self, req: AudioSourceRequest) -> SICMessage:
        if req.kind == "start":
            if req.key not in self._clips:
                if not req.path:
                    raise ValueError(f"Start request for key '{req.key}' missing path")

                sr, ch, data = self.load_wav_int16(
                    req.path,
                    target_sample_rate=self.sample_rate,
                    target_channels=self.channels,
                )
                self._clips[req.key] = data

            data = self._clips[req.key]

            if req.fade > 0.0:
                src = self.add_source(data, volume=0.0)
                src.fade_in(req.fade, final_volume=req.volume)
            else:
                src = self.add_source(data, volume=req.volume)

            self._sources_by_key[req.key] = src
            return SICMessage()  

        src = self._sources_by_key.get(req.key)
        if not src:
            return SICMessage() 

        if req.kind == "pause":
            if req.fade > 0.0:
                src.pause_with_fade(req.fade)
            else:
                src.pause()

        elif req.kind == "resume":
            if req.fade > 0.0:
                src.resume_with_fade(req.fade, final_volume=req.volume)
            else:
                src.resume()
                src.set_volume(req.volume)

        elif req.kind == "fade_out":
            src.fade_out(req.fade)

        elif req.kind == "stop":
            self.stop_source(src)
            del self._sources_by_key[req.key]

        else:
            raise ValueError(f"Unknown AudioSourceRequest kind: {req.kind}")

        return SICMessage()

    def _handle_mixer_request(self, req: AudioMixerRequest) -> SICMessage:
        kind = req.kind

        if kind == "next_chunk":
            pcm_chunk = self.next_chunk()
            return AudioMessage(pcm_chunk, self.params.sample_rate, True)

        elif kind == "stop_all":
            self.stop_all()
            self._sources_by_key.clear()

        elif kind == "clear_clips":
            self._clips.clear()

        elif kind == "reset":
            self.stop_all()
            self._sources_by_key.clear()
            self._clips.clear()

        else:
            raise ValueError(f"Unknown AudioMixerRequest kind: {kind}")

        return SICMessage()

    @staticmethod
    def get_inputs():
        return [AudioSourceRequest, AudioMixerRequest]

    @staticmethod
    def get_output():
        return AudioMessage

    @staticmethod
    def get_conf():
        return AudioMixerConf()

    def on_message(self, message):
        pass

    def on_request(self, request):
        if is_sic_instance(request, AudioSourceRequest):
            return self._handle_src_request(request)
        elif is_sic_instance(request, AudioMixerRequest):
            return self._handle_mixer_request(request)
        else:
            raise NotImplementedError("Unknown request type {}".format(type(request)))


class AudioMixer(SICConnector):
    component_class = AudioMixerComponent


if __name__ == "__main__":
    SICComponentManager([AudioMixerComponent], name="AudioMixer")
