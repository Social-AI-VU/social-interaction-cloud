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

To test the installation, use the utility script in ``sic_applications``.
Plug in the SpaceMouse and run:

.. code-block:: bash

    python sic_applications/utils/spacemouse_test.py

If this script prints changing ``x``, ``y``, and ``z`` values while you move the device, the setup is working.