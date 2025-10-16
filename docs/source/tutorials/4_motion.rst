4: Robot Motion
=======================================

This tutorial shows you how to play system motions, create, save, and replay custom motions, and how to stream motions from one robot to another.

📄 Nao Motion Tutorial
----------------------------

**Playing Animations and Setting Posture**
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

First, import the necessary functions from the SIC framework:

.. code-block:: python

    from sic_framework.devices import Nao  
    from sic_framework.devices.common_naoqi.naoqi_motion import NaoPostureRequest, NaoqiAnimationRequest  

Connect to the Nao (computer must be connected to the same network):

.. code-block:: python

    nao = Nao(ip="NAO_IP_HERE")

Set posture or play animation:

**To set the posture**: Second argument is the speed (NOTE: setting the speed too high may result in an error)

.. code-block:: python

    nao.motion.request(NaoPostureRequest("Stand", 0.5))

**To play an animation**: 

.. note::

    If you are playing a standing animation, make sure you put the Nao in a standing posture beforehand

.. code-block:: python

    nao.motion.request(NaoqiAnimationRequest("animations/Stand/Gestures/Hey_1"))

A list of all Nao animations can be found in the `Nao animation documentation <http://doc.aldebaran.com/2-4/naoqi/motion/alanimationplayer-advanced.html#animationplayer-list-behaviors-nao>`_.

A complete script for this tutorial can be found here: `demo_nao_motion.py <https://github.com/Social-AI-VU/sic_applications/blob/main/demos/nao/demo_nao_motion.py>`_


**Recording and Playing Custom Animations**
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

First, import the necessary functions from the SIC framework:

.. code-block:: python

    from sic_framework.devices import Nao  
    from sic_framework.devices.common_naoqi.naoqi_motion_recorder import (  
        NaoqiMotionRecording,  
        NaoqiMotionRecorderConf,  
        PlayRecording,  
        StartRecording,  
        StopRecording,  
    )  
    from sic_framework.devices.common_naoqi.naoqi_stiffness import Stiffness  

Connect to the Nao (computer must be connected to the same network):

.. code-block:: python

    nao = Nao(ip="NAO_IP_HERE")

Specify which Nao parts you want to record (NOTE: a 'chain' is a group of body parts, or a link of joints). The full list can be found in the `Nao body parts documentation <http://doc.aldebaran.com/2-8/family/nao_technical/bodyparts_naov6.html#nao-chains>`_.

.. code-block:: python

    chain = ["LArm", "RArm"]

Set the stiffness of these parts to 0 so that you can move them:

.. code-block:: python

    nao.stiffness.request(Stiffness(stiffness=0.0, joints=chain))  

Start the recording

    1. Set a 'record_time' variable. This is how long it will record the Nao's motion before saving it.

    2. It is recommended to include a message to indicate when to start moving the Nao

.. code-block:: python

    record_time = 10  
    print("Start moving the robot! (not too fast)")  

    nao.motion_record.request(StartRecording(chain))  

    time.sleep(record_time)  

Save the motion, give it a name:

.. code-block:: python

    recording = nao.motion_record.request(StopRecording())  
    recording.save(MOTION_NAME)  

Set the stiffness of the limbs to 0.7 so that the motors can move them. Play the recording back:

.. code-block:: python

    nao.stiffness.request(Stiffness(.7, chain))  

    recording = NaoqiMotionRecording.load(MOTION_NAME)  
    nao.motion_record.request(PlayRecording(recording))  

A complete script for this tutorial can be found here: `demo_nao_motion_recorder.py <https://github.com/Social-AI-VU/sic_applications/blob/main/demos/nao/demo_nao_motion_recorder.py>`_.
