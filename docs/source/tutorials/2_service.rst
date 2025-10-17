2: Using a Service
==========================

📄 SIC Services
----------------------------
The :doc:`Available services <../api/services>` page provides more details about which services are available, how to use them, and how to extend them.

In this example we will use the face detection service to draw a bounding box around a face that is detected in your laptop camera feed. It uses the ``sic_applications/demos`` `demo_desktop_camera_facedetection.py <https://github.com/Social-AI-VU/sic_applications/blob/main/demos/desktop/demo_desktop_camera_facedetection.py>`_.

**Step 1: starting Redis on your laptop**
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
The steps to starting Redis have been covered in :doc:`1: Installation and Setup <./1_installation>`

**Step 2: run the service**
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Services might need additional dependencies installed before being able to run them. You can install them with the appropriate service tag. For example,

.. code-block:: bash

   pip install --upgrade social-interaction-cloud[face-detection,dialogflow]  

A service can easily be run by opening a new terminal and calling the ``run-service`` command, for example ``run-face-detection`` or ``run-dialogflow``. See the :doc:`Available services <../api/services>`  page for more info about the dependencies and run commands for each service.

Note: the ``--upgrade`` flag ensures the new dependencies are installed if you already have previously installed the social interaction cloud.

For our example we will start the face-detection service.

**Ubuntu/Debian/MacOS**

.. toggle:: Ubuntu/Debian/MacOS
   
   .. code-block:: bash

      # Activate the same virtual environment where you pip installed  
      # social-interaction-cloud in the installation steps (e.g. in sic-applications)  
      source venv_sic/bin/activate  

      # First, install all the extra dependencies that this service depends on.  
      pip install --upgrade social-interaction-cloud[face-detection]  
      
      # Run the face-detection server  
      run-face-detection  

**Windows**

.. toggle:: Windows

   .. code-block:: bash

      # Activate the same virtual environment where you pip installed the  
      # social interaction cloud in the installation steps (e.g. in sic-applications)  
      source venv_sic/Scripts/activate  

      # First, install all the extra dependencies that this service depends on.  
      pip install --upgrade social-interaction-cloud[face-detection]  

      # Run the face-detection server  
      run-face-detection  

If successful, you should get the following output:

.. code-block:: bash

   [SICComponentManager 192.168.2.6]: INFO: Manager on device 192.168.2.6 starting  
   [SICComponentManager 192.168.2.6]: INFO: Started component manager on ip "192.168.2.6" with components:  
   [SICComponentManager 192.168.2.6]: INFO:  - FaceDetectionComponent  

**Step 3: running an application**
Run the demo file `demo_desktop_camera_facedetection.py <https://github.com/Social-AI-VU/sic_applications/blob/main/demos/desktop/demo_desktop_camera_facedetection.py>`_.

**Ubuntu/Debian/MacOS**

.. toggle:: Ubuntu/Debian/MacOS

   .. code-block:: bash

      # Activate the virtual environment in sic_applications  
      source venv_sic/bin/activate  

      # Go to sic_applications and the demo script  
      cd demos/desktop  
      python demo_desktop_camera_facedetection.py  

**Windows**

.. toggle:: Windows

   .. code-block:: bash

      # Activate the virtual environment in sic_applications  
      source venv_sic/Scripts/activate  

      # Go to sic_applications and the demo script  
      cd demos/desktop  
      python demo_desktop_camera_facedetection.py  

If all goes well, a display should pop up showing a bounding box around the detected face! If the image appears upside down, go to line 34 in ``demo_desktop_camera_facedetection.py`` and change the ``flip parameter`` to -1.
To understand how this example works, see the comments in the code. Next, we'll cover using a service that requires an API key.
