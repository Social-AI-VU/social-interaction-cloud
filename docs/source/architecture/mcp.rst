Model Context Protocol (MCP) in SIC
===================================

The `Model Context Protocol (MCP) <https://modelcontextprotocol.io/>`_ is an open protocol for connecting **hosts** (IDEs, agents, chat apps) to **servers** that expose **tools**, **resources**, and **prompts**. In SIC, MCP is the bridge between higher-level agents (for example a LangGraph assistant) and robot capabilities already implemented as SIC devices, connectors, and services.

Why MCP in SIC?
---------------

SIC already organizes hardware and algorithms as **components** with a Redis message layer. MCP adds a stable, vendor-neutral **tool surface** on top of that stack so that:

* **LLM agents** can call ``set_eye_color_name``, ``play_expression``, ``say_text``, and similar actions without bespoke glue code per demo.
* **External clients** (Cursor, Claude Desktop, custom scripts) can drive the same robot if they speak MCP.
* **One server process** can own the ``Nao`` (or stub) connection while several clients come and go over HTTP or stdio.

The reference implementation lives in ``sic_framework/mcp/mcp_nao_server.py`` (console entry point ``run-nao-mcp``). Demos that consume it are in ``sic_applications/demos/mcp/``.

Core ideas: JSON-RPC, tools, and REPL-style use
-----------------------------------------------

**JSON-RPC**

MCP messages are framed as **JSON-RPC 2.0** requests and responses (for example ``tools/list``, ``tools/call``). The client sends a method name and parameters; the server returns structured results or errors. This is the wire format regardless of whether bytes travel over stdio pipes or HTTP.

**Tools**

A **tool** is a named function the server advertises to clients. Each tool has a JSON schema for arguments. In SIC, tools typically wrap existing SIC requests (LED fades, TTS, motion catalog entries, and so on). Listing tools is how an agent discovers what it is allowed to do on the robot.

**REPL (read–eval–print loop)**

A **REPL** is an interactive loop: read user input, evaluate it, print output, repeat. The keyboard chat demo (``nao_mcp_chat_client.py``) is a REPL over typed text: each line becomes a user message to a LangGraph agent, which may call MCP tools before printing the assistant reply. The voice demo is the same pattern with speech-to-text filling in the “read” step. Neither REPL is part of MCP itself; they are application patterns built on top of MCP tool calls.

Transports supported by ``run-nao-mcp``
---------------------------------------

The NAO MCP server accepts ``--transport`` with three values. The transport chooses **how JSON-RPC bytes move** between client and server; it does not change which SIC components run on the robot.

.. list-table::
   :widths: 22 38 40
   :header-rows: 1

   * - Transport
     - Typical use
     - Notes
   * - ``stdio`` (default)
     - Parent process **spawns** the server as a subprocess; stdin/stdout carry JSON-RPC only.
     - **Required** when a SIC app starts MCP via ``langchain_mcp_adapters`` with ``command`` + ``args`` (see below). Nothing else may write to the child’s **stdout** or the stream is corrupted.
   * - ``sse``
     - Server listens on HTTP; client connects to a URL such as ``http://127.0.0.1:8000/sse``.
     - Good for a **long-lived server in its own terminal** while agents or demos connect from other processes.
   * - ``streamable-http``
     - Server listens on HTTP; client uses streamable HTTP MCP (URL often ``http://127.0.0.1:8000/mcp``).
     - Same “server in another tab” workflow as SSE; choose the transport that matches your MCP client library.

.. note::
   URLs are usually plain **HTTP** on localhost in development (not HTTPS), unless you terminate TLS in a reverse proxy yourself.

Effect on SIC logging
---------------------

SIC’s Redis client logger normally prints component and device lines to the terminal. That behavior conflicts with **stdio MCP**, because **stdout must be exclusively JSON-RPC**.

``mcp_nao_server.py`` therefore:

* Sets the global SIC client log threshold very high during **stdio** mode so Redis log lines are not printed to the terminal by default.
* Redirects the module-level ``sic_logging.print`` used for forwarded Redis logs to **stderr** instead of stdout.
* Writes file logs under ``sic_framework/mcp/logs/``.

When you start the server with **``sse``** or **``streamable-http``**, stdout is not the MCP byte stream. The server lowers the log threshold again so **INFO+ SIC logs go to stderr**, while JSON-RPC uses HTTP. You get a normal “robot + Redis” log experience in the server terminal.

.. warning::
   If you run **two SIC clients** against the same robot (for example a voice app plus an MCP server subprocess), you may see **duplicate** log lines with the same client IP: both processes subscribe to Redis and print forwarded robot events. That is not necessarily two robots—only two subscribers.

Ways to use MCP within SIC
--------------------------

Pattern 1: MCP server in its own process (HTTP)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Start the server first; connect any number of clients over SSE or streamable HTTP.

**Terminal 1 — server (owns ``Nao`` / Redis to robot):**

.. code-block:: bash

   pip install -e ".[mcp]"
   run-nao-mcp --transport sse --robot-ip <NAO_IP>

**Terminal 2 — keyboard chat agent (no direct robot connection):**

.. code-block:: bash

   # from sic_applications, with agent extras installed
   python demos/mcp/nao_mcp_chat_client.py --mcp-url http://127.0.0.1:8000/sse

Use ``--stub`` on the server to exercise tools without hardware. Use ``connect`` or ``ROBOT_IP`` / ``NAO_IP`` if you did not pass ``--robot-ip`` at startup.

Pattern 2: SIC application spawns MCP as a subprocess (stdio only)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Some demos (``nao_mcp_voice_client.py`` by default) start the server with **stdio**: the parent launches ``python -m sic_framework.mcp.mcp_nao_server`` and speaks MCP over pipes. **Only stdio supports this spawn model**; HTTP transports expect an already-listening server.

Implications:

* The parent often **also** connects to the robot (for example microphone → Google STT). The subprocess creates a **second** ``Nao()`` unless configured otherwise.
* Set ``SIC_NAO_REUSE_REMOTE_SIC=1`` in the subprocess environment (the voice demo does this) so the child **does not SSH-restart** the remote ``nao.py`` wrapper when Redis already sees a live component manager on the robot.
* Prefer **Pattern 1** (HTTP server in another tab) when debugging mic, STT, or Redis issues—it separates concerns and restores normal logging on the server terminal.

Pattern 3: External MCP host (Cursor, Claude Desktop, etc.)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Point the host at ``run-nao-mcp`` with **stdio** (command + args) or at an **HTTP URL** if the host supports SSE/streamable HTTP. The host’s agent loop is the “client”; SIC runs inside the server process. No SIC ``SICApplication`` is required in the host process.

NAO MCP tools (overview)
------------------------

Tools are defined in ``mcp_nao_server.py``. Common entries:

* **Connection:** ``connect``, ``shutdown_robot`` (alias ``shutdown_nao``)
* **Eyes / LEDs:** ``set_eye_color_rgb``, ``set_eye_color_name``
* **Audio / speech:** ``play_audio``, ``say_text``
* **Motion catalog:** ``get_expressions``, ``play_expression`` (see ``nao_expressions.py`` and ``expression_catalog.py``)

Stub mode (``--stub``) prints intended actions to stderr instead of calling the robot.

Installation and entry points
-----------------------------

Install MCP support with the optional extra:

.. code-block:: bash

   pip install -e ".[mcp]"

Console script:

.. code-block:: bash

   run-nao-mcp --help

Agent demos in ``sic_applications`` additionally need LangChain/LangGraph adapters (see that package’s ``mcp`` / ``nao-mcp-agent`` extras and ``conf/.env`` for API keys).

Related demos
-------------

.. list-table::
   :widths: 35 65
   :header-rows: 1

   * - Demo
     - Role
   * - ``sic_applications/demos/mcp/nao_mcp_chat_client.py``
     - Keyboard REPL; **requires** HTTP MCP server already running.
   * - ``sic_applications/demos/mcp/nao_mcp_voice_client.py``
     - NAO mic + Google STT; default **stdio** subprocess MCP; optional ``--mcp-url`` for HTTP.

Practical checklist
-------------------

#. Install ``social-interaction-cloud[mcp]`` (and demo deps if using agents).
#. Choose transport: **stdio** for subprocess spawn; **sse** / **streamable-http** for a dedicated server terminal.
#. Ensure **one** primary ``Nao`` connection path to the robot per session, or set ``SIC_NAO_REUSE_REMOTE_SIC=1`` for a secondary process.
#. Match client URL and transport to the server (``/sse`` vs ``/mcp``, ``streamable_http`` vs ``sse`` in adapter config).
#. After changing tool definitions, restart the MCP server (and any client that caches ``tools/list``).
