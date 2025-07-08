Introduction to the Social Interaction Cloud
============================================

This tutorial will guide you through the introduction to the Social Interaction Cloud framework.

📄 Getting Started with the Nao Robot
----------------------------

This guide will walk you through the process of getting started with the Nao robot.

For example, to show the camera feed of the robot:

In the `demo_nao_camera.py` file, make sure to adjust the ip adress to the ip adress of your robot. If you press the chest button of the robot it will tell you it’s ip adress. Ensure you are on the same network as the robot, and then you are good to go!

.. code-block:: python

    nao.setIP("192.168.1.100")

To start the camera demo from the terminal, use the following commands:

**Ubuntu/Debian/MacOS**
~~~~~~~~~~~~~~~~~~~~~~~~

.. toggle:: Ubuntu/Debian/MacOS

   .. code-block:: bash

      # Activate the same virtual environment where you pip installed 
      # social-interaction-cloud in the installation steps
      source venv_sic/bin/activate

      # Go to sic_applications and the demo script
      cd sic_applications/demos
      python demo_nao_camera.py

**Windows**
~~~~~~~~~~~
.. toggle:: Windows

   .. code-block:: bash

      # Activate the same virtual environment where you pip installed 
      # social-interaction-cloud in the installation steps
      .\.venv_sic\Scripts\activate

      # Go to sic_applications and the demo script
      cd sic_applications\demos
      python demo_nao_camera.py

.. note::

    It might take some time to start the demo file if the SIC has never been installed on the robot.

If all goes well, a display should pop up showing you the camera output of your robot!


📹: Video Tutorial (Windows)
----------------------------

.. raw:: html

    <iframe width="560" height="315" src="https://www.youtube.com/embed/3jOTnXRdTx0" title="YouTube video player" frameborder="0" allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture; web-share" referrerpolicy="strict-origin-when-cross-origin" allowfullscreen></iframe>
