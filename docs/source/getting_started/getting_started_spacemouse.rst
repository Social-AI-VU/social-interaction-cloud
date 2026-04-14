Getting started with the Spacemouse
=================================================

Installation
----------------------------

You need to install pyspacemouse.  There is an official installation guide in the `documentation <https://spacemouse.kubaandrysek.cz/>`_

The steps are as follows:

**Ubuntu/Debian**
~~~~~~~~~~~~~~~~~
.. toggle:: Ubuntu/Debian

    1. install HID API:

        .. code-block:: bash
            
            # install the library
            sudo apt-get install libhidapi-dev

            # set permissions
            echo 'KERNEL=="hidraw*", SUBSYSTEM=="hidraw", MODE="0664", GROUP="plugdev"' | sudo tee /etc/udev/rules.d/99-hidraw-permissions.rules
            sudo usermod -aG plugdev $USER
            newgrp plugdev

    2. install pyspacemouse:

       .. code-block:: bash

            pip install pyspacemouse

    3. set rules

       .. code-block:: bash

            sudo mkdir -p /etc/udev/rules.d/
            echo 'KERNEL=="hidraw*", SUBSYSTEM=="hidraw", MODE="0666", TAG+="uaccess", TAG+="udev-acl"' | sudo tee /etc/udev/rules.d/92-viia.rules
            sudo udevadm control --reload-rules
            sudo udevadm trigger

Verification/Usage
----------------------------

To test the correct installation or as a template for using the spacemouse in your code, here is an example script. Plug the spacemouse in and run the following script.

.. code-block:: python

    import pyspacemouse

    # Context manager (recommended) - automatically closes device
    with pyspacemouse.open() as device:
        while True:
            state = device.read()
            print(state.x, state.y, state.z)