from setuptools import find_packages, setup

# Basic (bare minimum) requirements for local machine
requirements = [
    "numpy",
    "opencv-python",
    "paramiko",
    "Pillow",
    "pyaudio",
    "PyTurboJPEG",
    "pyspacemouse",
    "python-dotenv",
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
    "whisper-speech-to-text": [
        "openai>=1.52.2",
        "SpeechRecognition>=3.11.0",
        "openai-whisper",
        "soundfile",
        "python-dotenv",
    ],
}

setup(
    name="social-interaction-cloud",
    version="2.0.20",
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
    python_requires=">=3.10,<3.13",
    entry_points={
        "console_scripts": [
            "run-dialogflow=sic_framework.services.dialogflow:main",
            "run-face-detection=sic_framework.services.face_detection:main",
            "run-face-detection-dnn=sic_framework.services.face_detection_dnn:main",
            "run-face-recognition=sic_framework.services.face_recognition_dnn:main",
            "run-gpt=sic_framework.services.openai_gpt:main",
            "run-whisper=sic_framework.services.openai_whisper_speech_to_text:main",
        ],
    },
)
