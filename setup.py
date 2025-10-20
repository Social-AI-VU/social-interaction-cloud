import sys
from setuptools import setup, find_packages

if sys.version_info[0] < 3:
    # Minimal fallback for Python 2
    setup(
        name="social-interaction-cloud",
        version="2.1.4",
        author="Koen Hindriks, Mike Ligthart",
        author_email="m.e.u.ligthart@vu.nl",
        packages=find_packages(),
        install_requires=[
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
        ],
    )
else:
    # For Python 3, defer to pyproject.toml / PEP 517
    from setuptools import setup
    setup()
