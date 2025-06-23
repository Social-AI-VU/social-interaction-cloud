1: Installation and Setup
======================

📄 Installation Guide
----------------------------

The Social Interaction Cloud (SIC) is a native python framework. It can be used via the social-interaction-cloud python package. The framework uses Redis for message brokering. To help you get started you can clone the sic_applications repository. Below you will find the basic instructions for cloning the repository and setting up the Social Interaction Cloud. 

Below you can find the installation instructions for Linux, MacOS, and Windows. 

In these instructions we will perform Git operations through a basic terminal and use Python's standard venv to create a virtual environment. If you're more familiar with other tools like PyCharm, VisualStudio, or Conda, feel free to use them instead. It is advised not to mix venvs. If you are going to use Python's standard venv, do not mix it with your conda environment, as it might lead to unexpected behavior.

**Ubuntu/Debian**
~~~~~~~~~~~~~~~~~

Use the following commands within a shell to install the Social Interaction Cloud framework on Ubuntu/Debian.

.. toggle:: Ubuntu/Debian

   .. code-block:: bash

      # Install git/redis/system dependencies for pyaudio
      sudo apt update
      sudo apt install git redis portaudio19-dev python3-pyaudio

      # Clone the sic_applications repo
      git clone https://github.com/Social-AI-VU/sic_applications.git

      # Create and activate virtual environment within the sic_applications folder
      cd sic_applications
      python -m venv venv_sic
      source venv_sic/bin/activate

      # Install social-interaction-cloud
      pip install social-interaction-cloud

      # Recommended on linux & mac: install libturbo-jpeg
      sudo apt-get install -y libturbojpeg
      pip install -U git+https://github.com/lilohuang/PyTurboJPEG.git


**MacOS**
~~~~~~~~~

Use the following commands within a shell to install the Social Interaction Cloud framework on MacOS.

.. toggle:: MacOS

   .. code-block:: bash

      # Install git/redis/system dependencies for pyaudio
      brew install git redis portaudio

      # Clone the sic_applications repo
      git clone https://github.com/Social-AI-VU/sic_applications.git

      # Create and activate virtual environment within the sic_applications folder
      cd sic_applications
      python -m venv venv_sic
      source venv_sic/bin/activate

      # Install social-interaction-cloud
      pip install social-interaction-cloud

      # Recommended on linux & mac: install libturbo-jpeg
      brew install jpeg-turbo
      pip install -U git+https://github.com/lilohuang/PyTurboJPEG.git


**Windows**
~~~~~~~~~~

.. toggle:: Windows

   For Windows users, the installation is not as as straightforward as for Ubuntu or Mac users, but it’s also fairly simple.

   Go to the official Git Download for Windows and download the latest version of the installer. A file named Git-2.xx.xx-64-bit.exe should be downloaded.

   Run the downloaded installer. You can keep the default settings by clicking Next through each step, and then click Install at the end.

   After installation, open Git Bash and run the following commands:

   .. code-block:: bash

      # Clone the sic_applications repo
      git clone https://github.com/Social-AI-VU/sic_applications.git
      
      # Create and activate virtual environment within the sic_applications folder
      cd sic_applications
      python -m venv venv_sic
      source venv_sic/Scripts/activate 

      # Install social-interaction-cloud
      pip install social-interaction-cloud

   Note: When a venv is activated, you should see parentheses with its name at the beginning of your terminal prompt, like:

   .. code-block:: bash

      (venv_sic) C:\Users\YourUsername\sic_applications>

   *(Optional) Install libturbo-jpeg:*

   Download and run the installer from `SourceForge <https://sourceforge.net/projects/libjpeg-turbo/files/2.1.5.1/libjpeg-turbo-2.1.5.1-gcc64.exe/download>`_

   Add the bin folder where you installed libjpeg-turb to the PATH environment variable (see e.g. `How to Edit the PATH Environment Variable on Windows 11 & 10 <https://www.wikihow.com/Change-the-PATH-Environment-Variable-on-Windows>`_ for how to do this)

   Make sure that the dll is called turbojpeg.dll (e.g. by copying and renaming libturbojpeg.dll)

   Pip Install PyTurboJPEG via

   .. code-block:: bash

      pip install -U git+https://github.com/lilohuang/PyTurboJPEG.git


📹: Video Tutorial (Windows)
----------------------------

.. raw:: html

    <iframe width="560" height="315" src="https://www.youtube.com/embed/iWvUm7mJOA8" title="YouTube video player" frameborder="0" allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture; web-share" referrerpolicy="strict-origin-when-cross-origin" allowfullscreen></iframe>
