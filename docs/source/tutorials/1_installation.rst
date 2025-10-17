1: Installation and Setup
==========================

📄 Installation Guide
----------------------------

The Social Interaction Cloud (SIC) is a native python framework. It can be used via the ``social-interaction-cloud`` `python package <https://pypi.org/project/social-interaction-cloud/>`_. The framework uses `Redis <https://redis.io/docs/latest/get-started/>`_ for message brokering. To help you get started you can clone the ``sic_applications`` `repository <https://github.com/Social-AI-VU/sic_applications/tree/main>`_. Below you will find the basic instructions for cloning the repository and setting up the Social Interaction Cloud. 

SIC requires :math:`3.10 \leq` python version :math:`\leq 3.12`.

Below you can find the installation instructions for Linux, MacOS, and Windows. 

In these instructions we will perform Git operations through a basic terminal and use Python's standard venv to create a virtual environment. If you're more familiar with other tools like PyCharm, VisualStudio, or Conda, feel free to use them instead. It is advised not to mix venvs. If you are going to use Python's standard venv, do not mix it with your conda environment, as it might lead to unexpected behavior.

**Ubuntu/Debian**
~~~~~~~~~~~~~~~~~


.. toggle:: Ubuntu/Debian

    Use the following commands within a shell to install the Social Interaction Cloud framework on Ubuntu/Debian.

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


.. toggle:: MacOS

    Use the following commands within a shell to install the Social Interaction Cloud framework on MacOS.

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
~~~~~~~~~~~

.. toggle:: Windows

   For Windows users, the installation is not as as straightforward as for Ubuntu or Mac users, but it’s also fairly simple.

   Go to the official Git `Download for Windows <https://git-scm.com/downloads/win>`_ and download the latest version of the installer. A file named **Git-2.xx.xx-64-bit.exe** should be downloaded.

   Run the downloaded installer. You can keep the default settings by clicking **Next** through each step, and then click **Install** at the end.

   After installation, open **Git Bash** and run the following commands:

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


**Upgrading SIC**
~~~~~~~~~~~~~~~~~
If you want to upgrade to the latest version, run this command in your venv:

   .. code-block:: bash

      pip install social-interaction-cloud --upgrade

**Running your first application**
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Running any application consists of two (or three) steps:

1. Start Redis

2. (Optional) If required, start a service, such as face detection

3. Run your program

We will run through a simple example: displaying your computer's camera feed on your screen.
The code for this example is available in the ``sic_applications/demos`` folder and called `demo_desktop_camera.py <https://github.com/Social-AI-VU/sic_applications/blob/main/demos/desktop/demo_desktop_camera.py>`_.

**Step 1: starting Redis on your laptop**
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

To enable communication between all your devices, we have to start Redis server. Make sure Redis is always up and running when you run any demos.

**Ubuntu/Debian/MacOS**

.. toggle:: Ubuntu/Debian/MacOS

   .. code-block:: bash

      # Navigate to the repo where you cloned the sic_applications
      cd sic_applications

      # Start the Redis server
      redis-server conf/redis/redis.conf

   For **Ubuntu/Debian** users, if you encounter the error *Could not create server TCP listening socket \*\:6379\: bind: Address already in use.*, please use the following command to stop the Redis server first

   .. code-block:: bash

      sudo systemctl stop redis-server.service  

   And, if you wish to prevent Redis server from starting automatically at boot, you can run

   .. code-block:: bash

      sudo systemctl disable redis-server.service  

   If you still can’t kill Redis server, you can use ``ps aux | grep redis-server`` command to find the PID (process ID) of the Redis server. And, terminate the process using ``kill PID``
   
   For **macOS** users, the process should be similar; just find the PID of the Redis server and kill the process:
   
   .. code-block:: bash

      lsof -i tcp:6379  

   And kill the pid shown:

   .. code-block:: bash

         kill -9 pid  

**Windows**

.. toggle:: Windows
   
   The commands below are for the Git Bash:

   .. code-block:: bash

      # Navigate to the repo where you cloned the sic_applications  
      cd sic_applications

      # Start the Redis server
      cd conf/redis  
      redis-server.exe redis.conf  

   If you encounter the error *Could not create server TCP listening socket \*\:6379\: bind: Address already in use.*, it means that port 6379 is already in use, probably by a previous instance of the Redis server that is still running in the background. You can either leave it as it is because it means that there is already a Redis server running, or if you really want to kill it and restart the server, find the PID and kill the program.
 
*Could not connect to redis at xxx.xxx.xxx.xxx*: If you have a problem connecting to the Redis server, even after running it in another terminal, it could be that your firewall is blocking communication from the robot. Please turn off your firewall to allow the robot to connect to the Redis server.

**Step 2: running an application**
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

To start the camera demo from the terminal, use the following commands.

**Ubuntu/Debian/MacOS**

.. toggle:: Ubuntu/Debian/MacOS

   .. code-block:: bash

      # Activate the same virtual environment where you pip installed  
      # social-interaction-cloud in the installation steps  
      source venv_sic/bin/activate  

      # Go to sic_applications and the demo script  
      cd sic_applications/demos/desktop  
      python demo_desktop_camera.py  

   For **macOS** users, you might get a warning to allow the python script to access your camera. Click allow, and start ``demo_desktop_camera.py`` again.

**Windows**

.. toggle:: Windows

   .. code-block:: bash

      # Activate the same virtual environment where you pip installed  
      # social-interaction-cloud in the installation steps  
      source venv_sic/Scripts/activate  

      # Go to sic_applications and the demo script  
      cd sic_applications/demos/desktop  
      python demo_desktop_camera.py  

If all goes well, a display should pop up showing you the camera output from your webcam!

.. note::
   If the camera output is flipped, change the ``flip`` parameter in the ``DesktopCameraConf`` from -1 to 1:

   .. code-block:: python

      conf = DesktopCameraConf(fx=1.0, fy=1.0, flip=1)  


And you should get the following output:

.. code-block:: bash

   [SICComponentManager 145.108.228.128]: INFO: Manager on device 145.108.228.128 starting  
   [SICComponentManager 145.108.228.128]: INFO: Started component manager on ip "145.108.228.128" with components:  
   [SICComponentManager 145.108.228.128]: INFO:  - DesktopMicrophoneSensor  
   [SICComponentManager 145.108.228.128]: INFO:  - DesktopCameraSensor  
   [SICComponentManager 145.108.228.128]: INFO:  - DesktopSpeakersActuator  
   [DesktopCameraSensor 145.108.228.128]: INFO: Starting sensor DesktopCameraSensor  
   [DesktopCameraSensor 145.108.228.128]: INFO: Started component DesktopCameraSensor  

**And that's it!**
To understand how this example works, see the comments in the code. Next, we'll start also using a service!