Docker in SIC
=============

SIC can run services in Docker containers so demos do not require you to start
Redis and every component service manually. This is optional: if an application
does not pass a compose file to ``SICApplication``, SIC assumes the required
services are already running.

How compose files work
----------------------

A demo can ask SIC to start a Docker Compose stack by passing a compose file:

.. code-block:: python

   app = SICApplication(services_compose="docker-compose.yml")

For class-based demos:

.. code-block:: python

   super(MyDemo, self).__init__(services_compose="docker-compose.yml")

The path is resolved relative to the demo file that creates the
``SICApplication``. During startup, SIC:

1. Resolves the compose file path.
2. Determines the compose project name from the top-level ``name:`` field.
3. Sets SIC-specific compose environment variables.
4. Builds missing service images when needed.
5. Runs ``docker compose up -d --wait``.
6. Waits until Redis is reachable on the host.

On shutdown, SIC runs ``docker compose down --remove-orphans`` for the same
compose project.

Creating a compose file
-----------------------

Start with a top-level ``name:`` so Docker Desktop and CLI commands show a stable
project name:

.. code-block:: yaml

   name: sic-my-demo

   services:
     redis:
       image: redis/redis-stack:latest
       ports:
         - "6379:6379"
       environment:
         REDIS_ARGS: "--requirepass changemeplease --appendonly yes"
       healthcheck:
         test: ["CMD", "redis-cli", "-a", "changemeplease", "ping"]
         interval: 2s
         timeout: 3s
         retries: 15

     gpt:
       build:
         context: ${SIC_BUILD_CONTEXT}
         dockerfile: ${SIC_DOCKER_ROOT}/docker/services/gpt/Dockerfile
         target: ${SIC_BUILD_TARGET}
         args:
           SIC_VERSION: ${SIC_VERSION}
       environment:
         SIC_IP: ${SIC_HOST_IP}
         DB_IP: redis
         DB_PORT: "6379"
         DB_PASS: changemeplease
       depends_on:
         redis:
           condition: service_healthy

Use ``DB_IP: redis`` inside containers because Redis is another compose service.
Use ``SIC_IP: ${SIC_HOST_IP}`` so services know how to identify the client host
running the SIC application.

The ``build.dockerfile`` entry is optional. If you provide it, Compose builds the
service image from SIC's Dockerfiles. If you use an ``image:`` instead, Compose
pulls or reuses that image. If neither a compose service nor a Dockerfile/image
is provided, then that SIC service must already be running manually.

Rebuilding containers
---------------------

SIC builds missing images automatically on first startup. Rebuild when:

- You changed a SIC Dockerfile.
- You changed service dependencies or package extras.
- You changed local SIC framework code and need the container to include it.
- A container is still running an older image than expected.

To force SIC to rebuild before starting:

.. code-block:: bash

   SIC_COMPOSE_REBUILD=1 python demo_RAG_chat.py

You can also rebuild manually from the demo directory:

.. code-block:: bash

   SIC_HOST_IP=<your-host-ip> docker compose -f docker-compose.yml -p sic-my-demo build

Then start the demo normally.

Looking at container logs
-------------------------

Use the compose project name from the top-level ``name:`` field:

.. code-block:: bash

   docker compose -f docker-compose.yml -p sic-my-demo logs
   docker compose -f docker-compose.yml -p sic-my-demo logs -f
   docker compose -f docker-compose.yml -p sic-my-demo logs -f gpt

Docker Desktop shows the same containers grouped under the compose project name.

How containers know the SIC version
-----------------------------------

When SIC starts a compose stack, it sets these environment variables for Compose:

``SIC_DOCKER_ROOT``
   Location of SIC's packaged Dockerfiles.

``SIC_BUILD_CONTEXT``
   The Docker build context. In a source checkout this is the repository root;
   in an installed package it is the package directory.

``SIC_BUILD_TARGET``
   ``local`` for source checkouts, ``pypi`` for installed packages.

``SIC_VERSION``
   The ``social-interaction-cloud`` package version. You can override it by
   setting ``SIC_VERSION`` yourself.

``SIC_HOST_IP``
   The host IP of the running SIC application. Services use this as ``SIC_IP``.

The service Dockerfiles use ``SIC_VERSION`` as a build argument. This lets
containers install the same released SIC package version as the host, unless you
are running from a local source checkout with the ``local`` build target.

Manual runs without compose
---------------------------

Compose is only a convenience. If you omit ``services_compose``:

.. code-block:: python

   app = SICApplication()

SIC does not start or stop any containers. In that mode, you must start Redis
and the service processes yourself, for example:

.. code-block:: bash

   run-redis
   run-gpt
   run-elevenlabs-tts

Use manual mode when:

- You are debugging a service directly in Python.
- A service runs on another machine.
- You already have Redis or a component manager running.
- You do not want Docker Desktop involved in the lifecycle.

Troubleshooting
---------------

``SIC_HOST_IP`` is missing
   You are probably running ``docker compose`` manually. Set it before the
   command:

   .. code-block:: bash

      SIC_HOST_IP=<your-host-ip> docker compose -f docker-compose.yml -p sic-my-demo up

Port ``6379`` is already allocated
   Another Redis container or local Redis process is running. Check:

   .. code-block:: bash

      docker ps --filter publish=6379

   Stop the old compose project:

   .. code-block:: bash

      docker compose -f docker-compose.yml -p sic-my-demo down --remove-orphans

Containers remain after Ctrl+C
   Make sure the demo is using the SIC checkout you edited. Prefer running with
   the project virtual environment rather than a system Python:

   .. code-block:: bash

      /path/to/.venv/bin/python demo_RAG_chat.py

   If you use ``sudo``, preserve the environment and explicit Python path:

   .. code-block:: bash

      sudo -E /path/to/.venv/bin/python demo_RAG_chat.py

Image changes are not picked up
   Rebuild with ``SIC_COMPOSE_REBUILD=1`` or run ``docker compose build``.

Service cannot connect to Redis
   Inside Docker, services should use ``DB_IP: redis``. Host-side SIC code should
   use ``127.0.0.1`` with the published port.
