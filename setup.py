from setuptools import Extension, find_packages, setup
from setuptools.command.build_ext import build_ext as _build_ext
import os
import subprocess
import sys

try:
    from setuptools.errors import CompileError, LibError, LinkError
except ImportError:  # Python 2 / older setuptools
    from distutils.errors import CompileError, LibError, LinkError


class LocalVQEExtension(Extension):
    """Marker extension: built by CMake in build_localvqe_ext, not distutils."""

    def __init__(self):
        Extension.__init__(
            self, "sic_framework.services.localvqe._liblocalvqe", sources=[]
        )


class build_localvqe_ext(_build_ext):
    """
    Compile LocalVQE's liblocalvqe.so (CMake) during the build phase.

    pip never tells setup.py which extras were requested, so this cannot be
    gated on the [localvqe] extra: it runs on every source build and degrades
    to a warning - never a failed SIC install - when the toolchain (git,
    cmake >= 3.20, C++17 compiler) is missing or the compile fails. Repair or
    rerun any time with `sic-build-localvqe`.
    """

    def run(self):
        native = [e for e in self.extensions if isinstance(e, LocalVQEExtension)]
        self.extensions = [
            e for e in self.extensions if not isinstance(e, LocalVQEExtension)
        ]
        _build_ext.run(self)
        if native:
            self._build_localvqe()

    def _build_localvqe(self):
        if sys.version_info[0] < 3:
            self._skip("requires Python 3 (robot installs never need it)")
            return
        import importlib.util

        script = os.path.join(
            os.path.dirname(os.path.abspath(__file__)),
            "sic_framework", "services", "localvqe", "build_localvqe.py",
        )
        spec = importlib.util.spec_from_file_location("_sic_localvqe_build", script)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        try:
            build_dir = module.build_for_setup()
        except (CompileError, LinkError, LibError) as e:
            self._skip("build failed: {}".format(e))
            return
        except (subprocess.CalledProcessError, OSError, RuntimeError) as e:
            self._skip("build failed: {}".format(e))
            return
        if build_dir is None:
            self._skip("required build tools missing (see messages above)")
            return
        if not self.inplace:
            # build_py copies package data before build_ext runs; mirror the
            # fresh libraries into the wheel's build tree as well.
            dest = os.path.join(
                self.build_lib, "sic_framework", "services", "localvqe", "lib"
            )
            module.copy_libs(build_dir, lib_dir=dest)

    def _skip(self, reason):
        print(
            "[sic-localvqe] LocalVQE native library not built: {}; install "
            "git/cmake >= 3.20/a C++17 compiler and reinstall, or run "
            "sic-build-localvqe. The rest of SIC installs normally.".format(reason)
        )

# Basic (bare minimum) requirements for local machine
requirements = [
    "numpy",
    "opencv-python",
    "paramiko",
    "Pillow",
    "pyaudio",
    "PyTurboJPEG",
    "redis",
    "scp",
    "six",
    "dotenv",
    "pathlib",
]

# Dependencies specific to each component or server.
# NOTE: Older setuptools on Python 2.7 is very strict about extras syntax.
# To keep installs working on Pepper/NAO (Python 2), we disable extras_require there.
if sys.version_info[0] == 2:
    extras_require = {}
else:
    extras_require = {
        "dev": [
            "black==24.10.0",
            "isort==5.13.2",
            "pre-commit==4.0.1",
            "twine",
            "wheel",
        ],
        "dialogflow": [
            "google-cloud-dialogflow",
        ],
        "dialogflow-cx": [
            "google-cloud-dialogflow-cx",
        ],
        "google-stt": [
            "google-cloud-speech",
        ],
        "google-tts": [
            "google-cloud-texttospeech",
        ],
        "face-detection-dnn": [
            "matplotlib",
            "pandas",
            "pyyaml",
            "torch",
            "torchvision",
            "tqdm",
            "requests",
        ],
        "face-recognition": [
            "scikit-learn",
            "torch",
            "torchvision",
        ],
        "object-detection": [
            "ultralytics",
        ],
        "openai-gpt": [
            "openai>=1.52.2",
            "python-dotenv",
        ],
        "webserver": [
            "Flask",
            "Flask-SocketIO",
        ],
        "whisper-speech-to-text": [
            "openai>=1.52.2",
            "SpeechRecognition>=3.11.0",
            "openai-whisper",
            "soundfile",
            "python-dotenv",
        ],
        "alphamini": [
            "alphamini",
            "protobuf==3.20.3",
            "websockets==13.1",
        ],
        # There is another dependency needed for Franka but it requires manual installation- panda-python
        # See Installation point 3 for instructions on installing the correct version: https://socialrobotics.atlassian.net/wiki/spaces/CBSR/pages/2412675074/Getting+started+with+Franka+Emika+Research+3#Installation%3A
        "franka": [
            "pyspacemouse",
            "scipy",
            "numpy<2.0.0",  # numpy 2.0.0 is not compatible with panda_py
        ],
        "docs": [
            "sphinx",
            "sphinx-togglebutton",
            "sphinx-rtd-theme",
            "sphinx-copybutton",
        ],
        "voice-detection": [
            "torch",
            "torchaudio",
            "numpy",
            "packaging",
        ],
        "nebula": [
            "openai>=1.52.2",
            "python-dotenv",
        ],
        "sortformer": [
            "pandas",
            "torch==2.9.0+cu130",
            "torchvision==0.24.0+cu130",
            "nemo_toolkit[asr]==2.5.2",
            "huggingface-hub==0.36.0",
        ],  # requires a flag to set the URL, e.g. pip install .[asr] --extra-index-url https://download.pytorch.org/whl/cu130
        "reachy-mini": [
            "reachy-mini[mujoco]>=1.6.0",
        ],
        "elevenlabs-tts": [
            "requests",
            "websockets==13.1",
        ],
        # LocalVQE (AEC + noise suppression + dereverb via GGML). Python-side
        # deps only: pip cannot tell setup.py which extras were requested, so
        # the native compile lives in build_ext (unconditional on source
        # builds) rather than behind this extra.
        "localvqe": [
            "numpy",
        ],
        "mcp": [
            "langchain-mcp-adapters>=0.1.0",
            "langchain>=0.3",
            "langchain-openai>=0.2",
            "langgraph>=1.0",
            "mcp>=1.0",
            "python-dotenv>=1.0.0",
        ],
    }

setup(
    name="social-interaction-cloud",
    version="2.2.3",
    author="Mike Ligthart",
    author_email="m.e.u.ligthart@vu.nl",
    long_description=open("README.md").read(),
    long_description_content_type="text/markdown",
    packages=find_packages(),
    package_data={
        "sic_framework": [
            "docker/**",
        ],
        "sic_framework.services.face_detection": [
            "haarcascade_frontalface_default.xml",
        ],
        "lib.libturbojpeg.lib32": [
            "libturbojpeg.so.0",
        ],
        # liblocalvqe.so + libggml*.so built by build_ext (build_localvqe_ext).
        "sic_framework.services.localvqe": [
            "lib/*.so*",
            "lib/*.dylib",
        ],
    },
    install_requires=requirements,
    extras_require=extras_require,
    # TODO this doesn't work with Python 2.7
    # python_requires=">=2.7, !=3.0.*, !=3.1.*, !=3.2.*, !=3.3.*, !=3.4.*, !=3.5.*, !=3.6.*, !=3.7.*, !=3.8.*, !=3.9.*, <3.13",
    entry_points={
        "console_scripts": [
            "run-dialogflow=sic_framework.services.dialogflow:main",
            "run-dialogflow-cx=sic_framework.services.dialogflow_cx:main",
            "run-face-detection=sic_framework.services.face_detection:main",
            "run-gpt=sic_framework.services.llm.openai_gpt:main",
            "run-whisper=sic_framework.services.openai_whisper_stt:main",
            "run-webserver=sic_framework.services.webserver.webserver_service:main",
            "run-google-tts=sic_framework.services.google_tts.google_tts:main",
            "run-elevenlabs-tts=sic_framework.services.elevenlabs_tts.elevenlabs_tts:main",
            "run-google-stt=sic_framework.services.google_stt.google_stt:main",
            "run-object-detection=sic_framework.services.object_detection:main",
            "run-voice-detection=sic_framework.services.voice_detection:main",
            "run-nebula=sic_framework.services.llm.nebula:main",
            "run-redis=sic_framework.services.datastore.redis_datastore:main",
            "run-sortformer=sic_framework.services.streaming_sortformer.stm_sortformer:main",
            "run-nao-mcp=sic_framework.mcp.nao.nao_mcp_server:main",
            "run-localvqe=sic_framework.services.localvqe.localvqe_service:main",
            "sic-build-localvqe=sic_framework.services.localvqe.build_localvqe:main",
        ],
    },
    ext_modules=[LocalVQEExtension()],
    cmdclass={
        "build_ext": build_localvqe_ext,
    },
)
