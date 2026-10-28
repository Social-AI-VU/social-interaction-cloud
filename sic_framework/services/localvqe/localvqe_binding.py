"""
localvqe_binding.py

Pure-ctypes binding for LocalVQE's GGML C API (liblocalvqe.so), modeled on
ggml/example_purego_test.go: dlopen + per-symbol argtypes, no compiled glue.
Signatures follow ggml/localvqe_api.h; audio is 16 kHz mono float32 in [-1, 1].
"""

import ctypes
import os
from ctypes import POINTER, c_char_p, c_float, c_int, c_int16, c_size_t

import numpy as np

PACKAGED_LIB_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "lib")

DEFAULT_MODEL_NAME = "localvqe-v1.3-4.8M-f32.gguf"
DEFAULT_MODEL_DIR = os.path.join("~", ".cache", "sic", "models")


class LocalVQEError(RuntimeError):
    """Raised when the native LocalVQE library reports an error."""


def default_lib_path():
    """Resolve liblocalvqe.so: $LOCALVQE_LIBRARY wins, then the packaged lib/ dir."""
    env = os.environ.get("LOCALVQE_LIBRARY")
    if env:
        return os.path.expanduser(env)
    return os.path.join(PACKAGED_LIB_DIR, "liblocalvqe.so")


def default_model_path():
    """$LOCALVQE_MODEL (a file path) wins, then ~/.cache/sic/models/<default gguf>."""
    env = os.environ.get("LOCALVQE_MODEL")
    if env:
        return os.path.expanduser(env)
    return os.path.join(os.path.expanduser(DEFAULT_MODEL_DIR), DEFAULT_MODEL_NAME)


# -- library loading and symbol registration (purego.RegisterLibFunc analog) --

# localvqe_ctx_t / localvqe_options_t are uintptr_t, i.e. pointer-sized ints.
_ctx_t = c_size_t
_opts_t = c_size_t

_SIGNATURES = {
    # name: (argtypes, restype)
    "localvqe_new": ([c_char_p], _ctx_t),
    "localvqe_new_with_frontend": ([c_char_p, c_char_p], _ctx_t),
    "localvqe_options_new": ([], _opts_t),
    "localvqe_options_free": ([_opts_t], None),
    "localvqe_options_set_model_path": ([_opts_t, c_char_p], c_int),
    "localvqe_options_set_backend": ([_opts_t, c_char_p], c_int),
    "localvqe_options_set_device": ([_opts_t, c_int], c_int),
    "localvqe_options_set_frontend_path": ([_opts_t, c_char_p], c_int),
    "localvqe_options_set_threads": ([_opts_t, c_int], c_int),
    "localvqe_new_with_options": ([_opts_t], _ctx_t),
    "localvqe_list_devices": ([], None),
    "localvqe_print_profile": ([_ctx_t], None),
    "localvqe_free": ([_ctx_t], None),
    "localvqe_process_f32": ([_ctx_t, POINTER(c_float), POINTER(c_float), c_int, POINTER(c_float)], c_int),
    "localvqe_process_s16": ([_ctx_t, POINTER(c_int16), POINTER(c_int16), c_int, POINTER(c_int16)], c_int),
    "localvqe_last_error": ([_ctx_t], c_char_p),
    "localvqe_sample_rate": ([_ctx_t], c_int),
    "localvqe_hop_length": ([_ctx_t], c_int),
    "localvqe_fft_size": ([_ctx_t], c_int),
    "localvqe_process_frame_f32": ([_ctx_t, POINTER(c_float), POINTER(c_float), c_int, POINTER(c_float)], c_int),
    "localvqe_process_frame_s16": ([_ctx_t, POINTER(c_int16), POINTER(c_int16), c_int, POINTER(c_int16)], c_int),
    "localvqe_reset": ([_ctx_t], None),
    "localvqe_set_noise_gate": ([_ctx_t, c_int, c_float], c_int),
    "localvqe_get_noise_gate": ([_ctx_t, POINTER(c_int), POINTER(c_float)], c_int),
}

_lib_cache = {}


def load_liblocalvqe(lib_path=None):
    """dlopen liblocalvqe.so and register argtypes/restype for every symbol."""
    path = os.path.abspath(lib_path or default_lib_path())
    if path in _lib_cache:
        return _lib_cache[path]

    if not os.path.isfile(path):
        raise LocalVQEError(
            f"liblocalvqe.so not found at {path}. The native build was skipped "
            f"during install (missing git/cmake/C++17 toolchain?); install the "
            f"tools and run: sic-build-localvqe\n"
            f"(override the location with $LOCALVQE_LIBRARY or the lib_path argument)"
        )

    # Mirrors purego.Dlopen(path, RTLD_LAZY); the library dladdr-locates its
    # co-located libggml-cpu-*.so backends itself.
    lib = ctypes.CDLL(path, mode=os.RTLD_LAZY | os.RTLD_LOCAL)

    for name, (argtypes, restype) in _SIGNATURES.items():
        try:
            fn = getattr(lib, name)
        except AttributeError:
            raise LocalVQEError(f"symbol {name} missing from {path} - library too old?")
        fn.argtypes = argtypes
        fn.restype = restype

    _lib_cache[path] = lib
    return lib


# -- int16 PCM <-> float32 helpers --

def pcm16_to_f32(data):
    """Convert int16 PCM (LE bytes or int16 ndarray) to float32 in [-1, 1]."""
    if isinstance(data, (bytes, bytearray, memoryview)):
        arr = np.frombuffer(data, dtype="<i2")
    else:
        arr = np.asarray(data, dtype=np.int16)
    return arr.astype(np.float32) / 32768.0


def f32_to_pcm16(samples):
    """Convert float32 samples in [-1, 1] to int16 PCM little-endian bytes."""
    arr = np.asarray(samples, dtype=np.float32)
    clipped = np.clip(arr, -1.0, 1.0)
    return (np.round(clipped * 32767.0)).astype("<i2").tobytes()


def _as_f32_buffer(x, name, length=None):
    """Validate/convert to a 1-D contiguous float32 array."""
    arr = np.ascontiguousarray(x, dtype=np.float32)
    if arr.ndim != 1:
        raise ValueError(f"{name} must be a 1-D array of mono samples, got shape {arr.shape}")
    if length is not None and arr.shape[0] != length:
        raise ValueError(f"{name} must have {length} samples, got {arr.shape[0]}")
    return arr


def _f32_ptr(arr):
    return arr.ctypes.data_as(POINTER(c_float))


# -- high-level wrapper (analog of the Go LocalVQE struct) --

class LocalVQE:
    """
    A LocalVQE inference context: AEC + noise suppression + dereverb on
    16 kHz mono audio.

    :param model_path: LocalVQE .gguf; None = $LOCALVQE_MODEL or the cache dir.
    :param threads: ggml CPU threads, None/0 = auto.
    :param backend: ggml backend name ("CPU", "Vulkan", ...), None = CPU.
    :param device: device index within the backend, None = 0.
    :param frontend_path: separate v1.4-AEC front-end gguf (GTCRN line only).
    :param noise_gate_dbfs: residual-echo gate threshold in dBFS, None = off.
    :param lib_path: liblocalvqe.so path; None = packaged lib dir.
    """

    def __init__(self, model_path=None, threads=None, backend=None, device=None,
                 frontend_path=None, noise_gate_dbfs=None, lib_path=None):
        self._ctx = 0
        self._lib = load_liblocalvqe(lib_path)

        model_path = os.path.expanduser(model_path or default_model_path())
        if not os.path.isfile(model_path):
            default_cache = os.path.join(
                os.path.expanduser(DEFAULT_MODEL_DIR), DEFAULT_MODEL_NAME
            )
            if model_path == default_cache:
                # First-start fetch of the default model. Deliberately not done
                # at build time: pip caches/moves wheels across machines, while
                # the model cache is per-machine.
                from sic_framework.services.localvqe import build_localvqe

                try:
                    build_localvqe.download_model()
                except Exception as e:
                    raise LocalVQEError(
                        f"could not download the default LocalVQE model to "
                        f"{model_path}: {e}\n"
                        f"retry, or run: sic-build-localvqe --skip-build --download-model"
                    )
            else:
                raise LocalVQEError(
                    f"LocalVQE model not found: {model_path}\n"
                    f"(point $LOCALVQE_MODEL / the model_path argument at a .gguf, "
                    f"or run: sic-build-localvqe --skip-build --download-model)"
                )

        if threads or backend or device is not None or frontend_path:
            opts = self._lib.localvqe_options_new()
            if not opts:
                raise LocalVQEError("localvqe_options_new failed")
            try:
                self._check_opt(opts, "model_path",
                                self._lib.localvqe_options_set_model_path(opts, model_path.encode("utf-8")))
                if threads:
                    self._check_opt(opts, "threads",
                                    self._lib.localvqe_options_set_threads(opts, int(threads)))
                if backend:
                    self._check_opt(opts, "backend",
                                    self._lib.localvqe_options_set_backend(opts, backend.encode("utf-8")))
                if device is not None:
                    self._check_opt(opts, "device",
                                    self._lib.localvqe_options_set_device(opts, int(device)))
                if frontend_path:
                    fe = os.path.expanduser(frontend_path)
                    self._check_opt(opts, "frontend_path",
                                    self._lib.localvqe_options_set_frontend_path(opts, fe.encode("utf-8")))
                self._ctx = self._lib.localvqe_new_with_options(opts)
            finally:
                self._lib.localvqe_options_free(opts)
        else:
            self._ctx = self._lib.localvqe_new(model_path.encode("utf-8"))

        if not self._ctx:
            raise LocalVQEError(
                f"localvqe_new failed for {model_path} "
                f"(backend={backend or 'CPU'}, device={device or 0})"
            )

        self.model_path = model_path
        self._sample_rate = int(self._lib.localvqe_sample_rate(self._ctx))
        self._hop_length = int(self._lib.localvqe_hop_length(self._ctx))
        self._fft_size = int(self._lib.localvqe_fft_size(self._ctx))

        if noise_gate_dbfs is not None:
            self.set_noise_gate(True, noise_gate_dbfs)

    @staticmethod
    def _check_opt(opts, what, rc):
        if rc != 0:
            raise LocalVQEError(f"localvqe_options_set_{what} failed (rc={rc})")

    # -- properties ---------------------------------------------------------

    @property
    def sample_rate(self):
        """Model sample rate in Hz (16000)."""
        return self._sample_rate

    @property
    def hop_length(self):
        """Streaming hop size in samples (256)."""
        return self._hop_length

    @property
    def fft_size(self):
        """Analysis FFT size in samples (512) - the minimum whole-clip length."""
        return self._fft_size

    # -- core API -----------------------------------------------------------

    def last_error(self):
        """Last error message from the native context, or ''."""
        if not self._ctx:
            return ""
        raw = self._lib.localvqe_last_error(self._ctx)
        return raw.decode("utf-8", "replace") if raw else ""

    def process(self, mic, ref=None, n_samples=None):
        """
        Whole-clip enhancement (localvqe_process_f32): 1-D float32 in [-1, 1],
        n_samples >= fft_size; ref None = zeros (NS + dereverb only).
        Returns enhanced float32, sample-aligned to the input.
        """
        self._ensure_open()
        mic = _as_f32_buffer(mic, "mic")
        if ref is None:
            ref = np.zeros_like(mic)
        else:
            ref = _as_f32_buffer(ref, "ref", length=mic.shape[0])
        if n_samples is None:
            n_samples = mic.shape[0]
        if n_samples > mic.shape[0]:
            raise ValueError(f"n_samples={n_samples} exceeds buffer length {mic.shape[0]}")
        if n_samples < self._fft_size:
            raise ValueError(
                f"localvqe_process_f32 needs n_samples >= {self._fft_size}, got {n_samples} "
                f"(use process_frame() for streaming hops)"
            )

        out = np.empty(n_samples, dtype=np.float32)
        rc = self._lib.localvqe_process_f32(
            self._ctx, _f32_ptr(mic), _f32_ptr(ref), int(n_samples), _f32_ptr(out)
        )
        if rc != 0:
            raise LocalVQEError(f"localvqe_process_f32 error {rc}: {self.last_error()}")
        return out

    def process_s16(self, mic, ref=None):
        """Whole-clip enhancement on int16 PCM (localvqe_process_s16)."""
        self._ensure_open()
        if isinstance(mic, (bytes, bytearray, memoryview)):
            mic = np.frombuffer(mic, dtype="<i2")
        mic = np.ascontiguousarray(mic, dtype=np.int16)
        if ref is None:
            ref = np.zeros_like(mic)
        else:
            if isinstance(ref, (bytes, bytearray, memoryview)):
                ref = np.frombuffer(ref, dtype="<i2")
            ref = np.ascontiguousarray(ref, dtype=np.int16)
            if ref.shape != mic.shape:
                raise ValueError("mic and ref must have the same length")
        n = mic.shape[0]
        if n < self._fft_size:
            raise ValueError(f"localvqe_process_s16 needs n_samples >= {self._fft_size}, got {n}")
        out = np.empty(n, dtype=np.int16)
        rc = self._lib.localvqe_process_s16(
            self._ctx,
            mic.ctypes.data_as(POINTER(c_int16)),
            ref.ctypes.data_as(POINTER(c_int16)),
            int(n),
            out.ctypes.data_as(POINTER(c_int16)),
        )
        if rc != 0:
            raise LocalVQEError(f"localvqe_process_s16 error {rc}: {self.last_error()}")
        return out

    def process_frame(self, mic, ref=None):
        """Streaming enhancement of one hop (256 float32 samples); ref None = zeros."""
        self._ensure_open()
        mic = _as_f32_buffer(mic, "mic", length=self._hop_length)
        if ref is None:
            ref = np.zeros_like(mic)
        else:
            ref = _as_f32_buffer(ref, "ref", length=self._hop_length)
        out = np.empty(self._hop_length, dtype=np.float32)
        rc = self._lib.localvqe_process_frame_f32(
            self._ctx, _f32_ptr(mic), _f32_ptr(ref), self._hop_length, _f32_ptr(out)
        )
        if rc != 0:
            raise LocalVQEError(f"localvqe_process_frame_f32 error {rc}: {self.last_error()}")
        return out

    def reset(self):
        """Reset streaming state to initial zeros (between utterances/streams)."""
        self._ensure_open()
        self._lib.localvqe_reset(self._ctx)

    def set_noise_gate(self, enabled, threshold_dbfs=-45.0):
        """Enable/disable the residual-echo noise gate (localvqe_set_noise_gate)."""
        self._ensure_open()
        rc = self._lib.localvqe_set_noise_gate(self._ctx, 1 if enabled else 0, float(threshold_dbfs))
        if rc != 0:
            raise LocalVQEError(f"localvqe_set_noise_gate error {rc}: {self.last_error()}")

    def get_noise_gate(self):
        """Return (enabled, threshold_dbfs) of the residual-echo noise gate."""
        self._ensure_open()
        enabled = c_int(0)
        threshold = c_float(0.0)
        rc = self._lib.localvqe_get_noise_gate(self._ctx, ctypes.byref(enabled), ctypes.byref(threshold))
        if rc != 0:
            raise LocalVQEError(f"localvqe_get_noise_gate error {rc}: {self.last_error()}")
        return bool(enabled.value), float(threshold.value)

    def print_profile(self):
        """Print memory budget + graph op histogram to stdout (diagnostic)."""
        self._ensure_open()
        self._lib.localvqe_print_profile(self._ctx)

    def close(self):
        """Free the native context (localvqe_free). Safe to call twice."""
        if self._ctx:
            self._lib.localvqe_free(self._ctx)
            self._ctx = 0

    def _ensure_open(self):
        if not self._ctx:
            raise LocalVQEError("LocalVQE context is closed")

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()

    def __del__(self):
        try:
            self.close()
        except Exception:
            pass


def list_devices(lib_path=None):
    """Print every registered ggml backend + device to stderr (no model needed)."""
    load_liblocalvqe(lib_path).localvqe_list_devices()


# -- parity self-test (python -m sic_framework.services.localvqe.localvqe_binding) --

def _read_wav_f32(path):
    import wave

    with wave.open(path, "rb") as w:
        assert w.getcomptype() == "NONE", f"{path}: compressed WAV not supported"
        assert w.getsampwidth() == 2, f"{path}: expected 16-bit PCM"
        assert w.getnchannels() == 1, f"{path}: expected mono"
        rate = w.getframerate()
        data = w.readframes(w.getnframes())
    return pcm16_to_f32(data), rate


def _write_wav_f32(path, samples, rate=16000):
    import wave

    with wave.open(path, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(f32_to_pcm16(samples))


def _synthetic_pair(seconds=2.0, rate=16000, seed=1234):
    """Deterministic mic/ref pair: ref tone mix, mic = speech-ish + echo + noise."""
    rng = np.random.default_rng(seed)
    n = int(seconds * rate)
    t = np.arange(n, dtype=np.float32) / rate
    ref = 0.30 * np.sin(2 * np.pi * 440.0 * t) + 0.15 * np.sin(2 * np.pi * 660.0 * t)
    ref = (ref * (0.5 + 0.5 * np.sin(2 * np.pi * 0.7 * t))).astype(np.float32)
    near = 0.25 * np.sin(2 * np.pi * 220.0 * t) * (np.sin(2 * np.pi * 2.0 * t) > 0)
    echo = 0.35 * np.concatenate([np.zeros(160, dtype=np.float32), ref[:-160]])
    noise = rng.normal(0.0, 0.01, n).astype(np.float32)
    mic = (near + echo + noise).astype(np.float32)
    return np.clip(mic, -1, 1), np.clip(ref, -1, 1)


def _selftest(argv=None):
    import argparse
    import subprocess
    import tempfile

    parser = argparse.ArgumentParser(description="LocalVQE ctypes binding parity self-test")
    parser.add_argument("--model", default=None, help="path to .gguf (default: default_model_path())")
    parser.add_argument("--lib", default=None, help="path to liblocalvqe.so")
    parser.add_argument("--mic", default=None, help="mic WAV (16 kHz mono s16); default: synthetic")
    parser.add_argument("--ref", default=None, help="far-end reference WAV; default: synthetic")
    parser.add_argument("--cli", default=None, help="path to the localvqe CLI for cross-checking")
    parser.add_argument("--out", default=None, help="write the enhanced audio to this WAV")
    parser.add_argument("--tol", type=float, default=1e-4, help="max abs diff tolerance (float domain)")
    args = parser.parse_args(argv)

    if args.mic:
        mic, rate = _read_wav_f32(args.mic)
        if args.ref:
            ref, ref_rate = _read_wav_f32(args.ref)
            assert ref_rate == rate, "mic/ref sample-rate mismatch"
            n = min(len(mic), len(ref))
            mic, ref = mic[:n], ref[:n]
        else:
            ref = np.zeros_like(mic)
    else:
        mic, ref = _synthetic_pair()
        rate = 16000

    vqe = LocalVQE(model_path=args.model, lib_path=args.lib)
    assert rate == vqe.sample_rate, f"input rate {rate} != model rate {vqe.sample_rate}"
    hop = vqe.hop_length
    n = (len(mic) // hop) * hop  # whole hops so streaming and batch cover the same span
    mic, ref = mic[:n], ref[:n]
    print(f"model={vqe.model_path}")
    print(f"sample_rate={vqe.sample_rate} hop={hop} fft={vqe.fft_size} n_samples={n}")

    # Whole clip
    whole = vqe.process(mic, ref)

    # Streaming: fresh state, then hop by hop
    vqe.reset()
    streamed = np.empty_like(whole)
    for i in range(0, n, hop):
        streamed[i:i + hop] = vqe.process_frame(mic[i:i + hop], ref[i:i + hop])

    diff = float(np.max(np.abs(streamed - whole)))
    rms = float(np.sqrt(np.mean((streamed - whole) ** 2)))
    ok = diff <= args.tol
    print(f"[stream-vs-whole] max_abs_diff={diff:.3e} rms_diff={rms:.3e} tol={args.tol:.1e} "
          f"-> {'PASS' if ok else 'FAIL'}")

    cli_ok = True
    if args.cli:
        with tempfile.TemporaryDirectory() as tmp:
            mic_wav = args.mic or os.path.join(tmp, "mic.wav")
            ref_wav = args.ref or os.path.join(tmp, "ref.wav")
            if not args.mic:
                _write_wav_f32(mic_wav, mic, rate)
                _write_wav_f32(ref_wav, ref, rate)
            out_wav = os.path.join(tmp, "cli_out.wav")
            cmd = [args.cli, vqe.model_path, "--in-wav", mic_wav, ref_wav, "--out-wav", out_wav]
            print("$ " + " ".join(cmd))
            subprocess.check_call(cmd)
            cli_out, cli_rate = _read_wav_f32(out_wav)
            assert cli_rate == rate
            m = min(len(cli_out), n)
            # compare in the int16 domain: both paths saw the same s16 wav input
            ours_i16 = np.frombuffer(f32_to_pcm16(whole[:m]), dtype="<i2")
            cli_i16 = np.frombuffer(f32_to_pcm16(cli_out[:m]), dtype="<i2")
            lsb = int(np.max(np.abs(ours_i16.astype(np.int32) - cli_i16.astype(np.int32))))
            cli_ok = lsb <= 2  # allow rounding differences in the last bits
            print(f"[binding-vs-cli] max_abs_diff={lsb} LSB (int16) over {m} samples "
                  f"-> {'PASS' if cli_ok else 'FAIL'}")

    if args.out:
        _write_wav_f32(args.out, whole, rate)
        print(f"enhanced audio written to {args.out}")

    vqe.close()
    return 0 if (ok and cli_ok) else 1


if __name__ == "__main__":
    import sys

    sys.exit(_selftest())
