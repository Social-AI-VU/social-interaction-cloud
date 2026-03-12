Getting started with Alphamini
===============================

Overview
--------

The Alphamini robot runs Android internally and provides an official Python SDK
(`mini_sdk`) for motion, LEDs, face expressions, and other capabilities.
However, the SDK does **not** expose continuous streaming for the on‑board
microphone or camera.

To integrate Alphamini's audio and video into SIC, we therefore provide custom
Android applications that:

- run directly on the Alphamini,
- connect back to SIC via local TCP sockets, and
- stream compressed audio and video frames into the SIC framework.

This page explains:

- why custom Android apps are needed for microphone and camera streaming,
- how to install these apps onto a Mini using ``adb`` over USB, and
- which tools (ADB, Android Studio, Vysor) are useful when working with Alphamini.


Why custom Android apps are needed
----------------------------------

The Alphamini SDK is designed around discrete commands (e.g., move, speak,
play animation) rather than continuous media pipelines. In particular:

- there is **no built‑in API** to expose a live microphone stream to your own
  process on the robot;
- there is **no built‑in API** to expose a live camera frame stream with
  controllable resolution, compression, and frame rate.

To work around this, SIC ships standalone Android apps that run on the robot:

- a **camera app** that

  - opens the Alphamini camera with the Android Camera API,
  - encodes preview frames as JPEG, and
  - streams them over TCP to a SIC component (e.g. ``MiniCameraSensor``);

- a **microphone app** that

  - captures PCM audio from the Android audio stack,
  - chunks and (optionally) compresses samples, and
  - streams them over TCP to a SIC component (e.g. ``MiniMicrophoneSensor``).

On the SIC side, Python components (running in Termux on the robot) act as
servers that:

- accept TCP connections from these Android apps,
- decode the incoming byte streams (audio or images), and
- publish them into SIC/Redis as standard SIC messages.


Tooling: ADB, Android Studio, and Vysor
---------------------------------------

ADB (Android Debug Bridge)
~~~~~~~~~~~~~~~~~~~~~~~~~~

**ADB** is a command‑line tool used to communicate with Android devices. It
allows you to:

- install and uninstall APKs,
- view logs (``adb logcat``),
- run shell commands (``adb shell``).

For Alphamini, ADB is the primary way to:

- install or update the custom microphone and camera apps,
- inspect logs from those apps while they interact with SIC,
- and debug issues in the media pipeline.


Android Studio
~~~~~~~~~~~~~~

**Android Studio** is the official IDE for Android development. It provides:

- a code editor with Android‑specific tooling,
- Gradle build integration,
- device and emulator management,
- and a graphical interface for installing and debugging apps.

You do *not* strictly need Android Studio to deploy APKs (you can use plain
``adb install``), but it is very helpful for:

- editing and building the Alphamini camera/microphone apps,
- running them on a test device or on the Alphamini,
- and inspecting performance, logs, and exceptions during development.


Vysor
~~~~~

**Vysor** is a desktop tool that mirrors an Android device’s screen to your
computer and lets you control it with mouse/keyboard. For Alphamini, Vysor is
useful because:

- the robot does not have an easily accessible touch screen in the usual sense,
- you often want to *see* what the Android UI is doing (camera preview, error
  dialogs, permissions prompts),
- and you may need to grant permissions or confirm prompts the first time an
  app runs.

In practice, Vysor lets you interact with the Alphamini’s Android UI as if it
were a phone attached to your computer.


Installing ADB on your computer
-------------------------------

On macOS, the easiest way to install the Android platform tools (including ADB)
is via Homebrew:

.. code-block:: bash

   brew install --cask android-platform-tools

Verify that ``adb`` is available:

.. code-block:: bash

   adb version

You should see version information printed to the terminal.


Connecting to Alphamini with ADB (USB)
--------------------------------------

For this workflow we **use USB only** and do *not* rely on ADB over the
network, to avoid extra configuration and authentication issues.

1. Connect Alphamini to your computer via USB.
2. In a terminal:

   .. code-block:: bash

      adb devices

3. Once the device appears as ``device``, you can install APKs, view logs, and
   run shell commands.


Installing the Alphamini camera and microphone apps
---------------------------------------------------

Prerequisites
~~~~~~~~~~~~~

- The camera and microphone Android apps have been built into APK files
  (for example, ``camera_app-debug.apk`` and ``microphone_app-debug.apk``).
- ``adb devices`` lists your Alphamini as ``device`` over USB.

Installing via ADB (USB)
~~~~~~~~~~~~~~~~~~~~~~~~

From the directory where your APK is located:

.. code-block:: bash

   # First install
   adb install camera_app-debug.apk

   # If updating an existing install
   adb install -r camera_app-debug.apk

Repeat this for the microphone app if it is a separate APK.

Once installed, the apps will appear in the Alphamini’s Android launcher, and
SIC components (e.g. ``MiniCameraSensor`` / ``MiniMicrophoneSensor``) can start
them via the Android Activity Manager (``am``) inside Termux.


Using Vysor with Alphamini
--------------------------

To observe and interact with the Alphamini’s Android UI:

1. Connect Alphamini to your computer via USB.
2. Open Vysor and select the Alphamini device.
3. You should now see the Alphamini’s Android home screen mirrored on your
   desktop.

Typical uses:

- confirm that the camera or microphone app is in the foreground and running;
- grant camera/microphone permissions the first time the app is launched;
- observe whether the camera preview or recording UI looks correct while SIC
  is running;
- manually stop or start the app if needed during debugging.


How this ties into SIC
----------------------

The overall data flow is:

- On Alphamini:

  - Termux runs the SIC device script (``alphamini.py``) and the media
    components (``MiniCameraSensor``, ``MiniMicrophoneSensor``).
  - These components open local TCP server sockets (e.g., ``127.0.0.1:6001`` for
    camera, and another port for microphone).

- On Android (same device):

  - The camera and microphone apps connect to those local sockets.
  - They stream encoded frames/samples according to simple binary protocols
    (length headers + compressed payload).

- On your development machine:

  - A SIC application (for example, a demo script) connects to the remote SIC
    device,
  - subscribes to the media components, and
  - receives decoded images/audio.

In this architecture, ADB, Android Studio, and Vysor are tooling layers that
help you build, install, observe, and debug the Android side of the pipeline,
while SIC components and Python code manage the robot‑facing and
application‑facing parts of the integration.

