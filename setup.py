from setuptools import find_packages, setup

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
]

# Dependencies specific to each component or server
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
    ],
}

setup(
    name="social-interaction-cloud",
    version="2.0.40",
    author="Koen Hindriks",
    author_email="k.v.hindriks@vu.nl",
    long_description=open("README.md").read(),
    long_description_content_type="text/markdown",
    packages=find_packages(),
    package_data={
        "sic_framework.services.face_detection": [
            "haarcascade_frontalface_default.xml",
        ],
        "lib.libturbojpeg.lib32": [
            "libturbojpeg.so.0",
        ],
    },
    install_requires=requirements,
    extras_require=extras_require,
    # TODO this doesn't work with Python 2.7
    # python_requires=">=2.7, !=3.0.*, !=3.1.*, !=3.2.*, !=3.3.*, !=3.4.*, !=3.5.*, !=3.6.*, !=3.7.*, !=3.8.*, !=3.9.*, <3.13",
    entry_points={
        "console_scripts": [
            "run-dialogflow=sic_framework.services.dialogflow:main",
            "run-face-detection=sic_framework.services.face_detection:main",
            "run-face-detection-dnn=sic_framework.services.face_detection_dnn:main",
            "run-face-recognition=sic_framework.services.face_recognition_dnn:main",
            "run-gpt=sic_framework.services.openai_gpt:main",
            "run-whisper=sic_framework.services.openai_whisper_stt:main",
            "run-webserver=sic_framework.services.webserver.webserver_component:main",
            "run-google-tts=sic_framework.services.google_tts.google_tts:main",
            "run-google-stt=sic_framework.services.google_stt.google_stt:main",
        ],
    },
)
