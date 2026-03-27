Getting started with the robots
===============================

This page contains information on how to get started with the various robots.

Getting started with the Nao
----------------------------------
.. toctree::
   :maxdepth: 2

   getting_started/getting_started_nao


Getting started with the Franka Emika robot arm
------------------------------------------------
.. toctree::
   :maxdepth: 2

   getting_started/getting_started_franka


Getting started with the Alphamini
----------------------------------
.. toctree::
   :maxdepth: 2

   getting_started/getting_started_alphamini

- Each robot has its own installation process, depending on its operating system and device specific constraints. For example, the Alphamini requires SSH to first be installed before SIC can be installed.
- Test environments for development purposes are also set up differently per robot for the same reason.
- Each device consists of different components and controls. Components run directly on the robot and be controlled through Connectors. Other functionality is implemented within the device class itself via an SDK (for example with the Alphamini's Mini SDK).
- Devices may be a hybrid of Component/Connector control and SDK control. See the device-specific documentation in :doc:`api/devices` for details.