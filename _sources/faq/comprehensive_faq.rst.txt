Comprehensive FAQ
==================

Frequently Asked Questions and Solutions for the Social Interaction Cloud framework.

General Troubleshooting Advice:

1. Sometimes there are permission differences between using a shell within an IDE or standalone terminal. Try running the commands in a standalone terminal or using a sudo command.

2. Firewalls can sometimes block network communication. You may need to turn off your firewall.

3. If you are using WSL, WSL uses a virtual IP, which causes connection issues. See the Windows WSL Connection Issues section for more details.


.. note::
   If your issue is not covered here, please check the `troubleshooting forum <https://github.com/Social-AI-VU/social-interaction-cloud/discussions/64>`_.


Redis address already in use
----------------------------

.. toggle::

   **Problem:** Redis port 6379 is already being used by another process.

   **Solution:** This likely means Redis is already running. You can either leave it be and proceed or kill the existing Redis processes:

   .. code-block:: bash

      # Kill Redis processes
      sudo pkill redis-server

   If on MacOS or Linux, you can also try running the redic_close.sh script found within the sic_appplications repository.


Could not connect to Redis server
----------------------------------

.. toggle::

   **Problem:** Cannot connect to Redis server.

   **Solution:** 
   
   1. Make sure Redis server is running.
   2. Try running Redis in another terminal.
   3. It could be that your firewall is blocking communication from the robot. Please turn off your firewall to allow the robot to connect to the Redis server.


Could not connect to component
-------------------------------

.. toggle::

   **Problem:** "Could not connect to YourComponentNameHere on device 192.168.0.xxx"

   **Solution:** 
   This could have many different causes, but there are a few things to check:

   1. Check the IP address of the robot is correct. Press the chest button to find out.

   2. Make sure the component is running, if it is not a desktop or robot component. E.g. Dialogflow and Whisper have to be started separately.

   3. You are using the desktop or robot components directly. Use the Nao(ip=...)/Pepper(ip=...)/Desktop() wrappers which will start the components for you.


Cannot connect to robot from IDE terminal
-----------------------------------------

.. toggle::

   **Problem:** Cannot connect to NAO or Pepper robots when running scripts from an IDE terminal (e.g. VSCode), but connection works fine from standalone terminal.

   **Solution:**
   
   Some IDEs such as VSCode sandbox terminal permissions, which can prevent SSH connections to robots. Try one of these solutions:

   **Option 1:** Run the script with ``sudo`` from within VSCode:

   .. code-block:: bash

      sudo python3 your_script.py

   **Option 2:** Run your script from a standalone terminal (outside VSCode) instead of the integrated terminal.

   .. note::
      The permission sandboxing is a security feature of VSCode. If the standalone terminal works,
      the issue is specifically related to VSCode's terminal permissions, not your network or robot configuration.


Windows WSL Connection Issues
------------------------------

.. toggle::

   **Problem:**
   
   If you are using WSL, WSL uses a virtual IP, which prevents the robot from connecting directly.

   **Solution:** 
   
   1. Enable port forwarding to redirect traffic from the native Windows port to the WSL virtual port. To do this, open PowerShell (run as admin) and run the following command (replace WSL_IP with your WSL virtual IP):

   .. code-block:: bash

      netsh interface portproxy add v4tov4 listenport=6379 listenaddress=0.0.0.0 connectport=6379 connectaddress=WSL_IP

   2. In an environment variable, you need to manually pass your native Windows IP for now, because SIC can currently only retrieve the IP of the environment it’s running in—which is the virtual IP, not your native Windows IP:

   .. code-block:: bash

      DB_IP="10.x.x.x"

   3. You may need to define this in a file and manually load it using `load_dotenv()`.


Animation wrong path format error
----------------------------------

.. toggle::

   **Problem:** "RuntimeError: Wrong path format (animations/Stand/BodyTalk/BodyTalk_1) which has been converted in: animations/Stand/BodyTalk/BodyTalk_1, it should follow the pattern: package/path"

   **Solution:** 
   BodyTalk/BodyTalk_XX does not work on the NAO’s as of 16/11/2023. The Gestures do work, so try those instead (possible to record your own).


Camera output not showing
-------------------------

.. toggle::

   **Problem:** The camera output does not display on screen.

   **Solution:** 
   Solution A: run in own terminal or VS code, not in pycharm terminal.

   Solution B: On MacOS you can only use cv2.imshow from the main thread, not from other threads or callbacks (which use threads).

   Solution C: Test that the opencv module is working by writing a simple Python script that uses it.

   Solution D: If you are using WSL, OpenCV’s `imshow` can’t display an image because WSL doesn’t support GUI applications by default. You probably need to install an X server.


Personal Apple device sensors being used
-----------------------------------------

.. toggle::

   **Problem:** Personal Apple device sensors (camera/microphone) are being used instead of the Desktop's.

   **Solution:**
   On Mac you can turn off "Continuity Camera" or 

   On your iPhone, go to Settings > General > AirPlay & Handoff. Turn off Continuity Camera


Portaudio.h file not found
---------------------------

.. toggle::

   **Problem:** "Portaudio.h file not found" when installing PyAudio.

   **Solution:**

   On MacOs

   .. code-block:: bash

      brew install portaudio
      pip install pyaudio
      pip install opencv-python six

   On Ubuntu

   .. code-block:: bash

      sudo apt install portaudio19-dev python3-pyaudio
      pip install pyaudio
      pip install opencv-python six


ImportError: libGL.so.1: cannot open shared object file
-------------------------------------------------------

.. toggle::

   **Problem:** ImportError: libGL.so.1: cannot open shared object file: No such file or directory.

   **Solution:**

   .. code-block:: bash

      sudo apt-get install python3-opencv


Incompatible architecture [Mac]
--------------------------------

.. toggle::

   **Problem:** Have ‘arm64’, need ‘x86_64’, this seems to affect the newer macbooks only.

   Someone once fixed this by trying different answers from `this stackoverflow question <https://stackoverflow.com/questions/71882029/mach-o-file-but-is-an-incompatible-architecture-have-arm64-need-x86-64-i>`_


Could not build wheels for opencv-python
-----------------------------------------

.. toggle::

   **Problem:** Could not build wheels for opencv-python.

   **Solution:**

   Try using an earlier version of opencv-python.

   .. code-block:: bash

      pip install opencv-python==4.8.1.78


Very laggy camera output
------------------------

.. toggle::

   **Problem:** The camera output is very laggy.

   **Solution:**

   Make sure libturbo-jpeg is installed. See :doc:`../tutorials/1_installation` for more details for your OS.


Image is tinted blue
------------------------

.. toggle::

   **Problem:** Image is tinted blue when using cv2 library.

   **Solution:**

   Try adding the following line to the code:

   .. code-block:: python

      img = cv2.cvtColor(img, cv2.COLOR_RGB2BGR)


Webcam output is flipped
------------------------

.. toggle::

   **Problem:** Webcam output is flipped.

   **Solution:**

   Try adding the following line to the code:

   .. code-block:: python

      img = cv2.flip(img, 0)
