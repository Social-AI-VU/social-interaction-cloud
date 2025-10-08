Processes and Threads
=======================================

A SIC application is a collection of processes and threads that run across multiple devices, coordinated through Redis messaging.

Process Architecture
--------------------

SIC applications consist of two main types of processes:

**Client-side (SIC Application)**
    - Runs the main application logic
    - Contains Connectors and DeviceManagers
    - Orchestrates component interactions through Redis
    - Handles graceful shutdown and cleanup

**Server-side (Component Managers)**
    - Manages component lifecycle on each device
    - Started by commands like ``run-face-detection`` or by DeviceManagers
    - Can run locally (Desktop) or remotely (NAO, Pepper, etc.)
    - Each Component Manager can host multiple Components but only of specified types.

Each process gets its own RedisConnection instance, which is used to communicate with the Redis server.

Thread Types
------------

**Redis Subscriber Threads**
    These threads listen to Redis channels and handle incoming messages:

    **Component Handler Threads**
        - Handle incoming messages and requests for components
        - Created by ``register_message_handler()`` and ``register_request_handler()``
        - Named like "ComponentName_message_handler" or "ComponentName_request_handler"
        - Execute component's ``on_message()`` and ``on_request()`` methods

    **Application Callback Threads**
        - Created when applications register callbacks with ``register_callback()``
        - Process component output before sending to other components
        - Named like "ComponentEndpoint_callback"
        - Allow custom processing of component data

    **Request-Reply Threads**
        - Created temporarily when sending requests via ``request()``
        - Subscribe to reply channels and wait for responses
        - Automatically cleaned up after receiving replies

**Component Main Threads**
    - Created when a ComponentManager starts a Component
    - Some such as Sensors enter a loop that continuously produces output; Others just initialize an API (such as GPT, Dialogflow)

**Device Management Threads**   

    **SSH Monitor Threads**
        - Created by DeviceManagers for remote devices
        - Monitor SSH connections and remote process status
        - Detect when remote processes stop unexpectedly

    **Local Component Manager Threads**
        - For local devices (Desktop, Franka), Component Managers run in threads
        - Run as daemon threads to avoid blocking main application

Shutdown Process
----------------

.. image:: /_static/app_shutdown_process.drawio.svg
   :alt: Application Shutdown Process
   :align: center
