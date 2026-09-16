Model Context Protocol (MCP) in SIC
===================================

The `Model Context Protocol (MCP) <https://modelcontextprotocol.io/>`_ is an open protocol for connecting hosts (IDEs, agents, chat apps) to servers that expose tools, resources, and prompts. In SIC, MCP is the bridge between higher-level agents (for example a LangGraph assistant) and robot capabilities already implemented as SIC devices, connectors, and services.

Why MCP in SIC?
---------------

SIC already organizes hardware and algorithms as components with a Redis message layer. MCP adds a stable, vendor-neutral tool surface on top of that stack so that:

* LLM agents can call robot actions through named tools instead of bespoke glue per demo.
* One MCP server subprocess owns the robot connection (and any sensors tied to that server, such as a microphone for speech input) while a separate demo client drives the agent loop.
* External MCP hosts (Cursor, Claude Desktop, custom scripts) can spawn or connect to a robot-specific MCP server entry point.

Layout in the codebase
----------------------

Robot-agnostic shared code lives at the top of ``sic_framework/mcp/``:

* ``mcp_server.py`` — file-only logging, ``run_mcp_server()`` CLI wrapper, ``SICMcpServer`` base class.
* ``mcp_client.py`` — ``McpRobotClientConfig``, ``mcp_stdio_connection()``, robot IP resolution, spawn error hints.
* ``expression_catalog.py`` — shared JSON shape for motion/expression catalogs (``get_expressions`` / ``play_expression`` tools).

Each supported robot has its own package under ``sic_framework/mcp/<robot>/`` (server module, client helpers, and robot-specific catalogs). Demos mirror that layout under ``sic_applications/demos/mcp/<robot>/``.

Today only NAO is implemented; see `NAO (reference implementation)`_ below. Additional robots should follow the same split: shared MCP runtime in ``sic_framework/mcp/``, robot tools and device wiring in ``sic_framework/mcp/<robot>/``.

Core ideas: JSON-RPC, tools, and REPL-style use
-----------------------------------------------

JSON-RPC
~~~~~~~~

MCP messages are framed as JSON-RPC 2.0 requests and responses (for example ``tools/list``, ``tools/call``). The client sends a method name and parameters; the server returns structured results or errors. In the SIC demo workflow, JSON-RPC travels over stdio between a LangChain parent process and a spawned MCP server child.

Tools
~~~~~

A tool is a named function the server advertises to clients. Each tool has a JSON schema for arguments. In SIC, tools typically wrap existing SIC requests (LEDs, TTS, motion, speech, and so on). Listing tools is how an agent discovers what it is allowed to do on the robot.

REPL (read-eval-print loop)
~~~~~~~~~~~~~~~~~~~~~~~~~~~

A REPL is an interactive loop: read user input, evaluate it, print output, repeat. A keyboard chat demo is a REPL over typed text: each line becomes a user message to a LangGraph agent, which may call MCP tools before printing the assistant reply. A voice demo uses the same pattern, but the demo client calls a blocking listen tool on the MCP server each turn and passes the transcript to the agent. Neither REPL is part of MCP itself; they are application patterns built on top of MCP tool calls.

Architecture: LangGraph client + stdio MCP server
-------------------------------------------------

This is the workflow used by SIC agent demos today.

#. A demo client (subclass of ``SICApplication``) builds a ``MultiServerMCPClient`` connection dict via ``mcp_stdio_connection()`` and a robot-specific ``McpRobotClientConfig``.
#. LangChain spawns the robot's MCP server module (``python -m sic_framework.mcp.<robot>.<robot>_mcp_server``) with ``--robot-ip``, required ``--log-dir``, and optional ``--stub``.
#. The MCP server connects to the hardware, registers tools, and performs all robot I/O. The parent demo process does not open a parallel device connection for those tool calls.
#. The demo runs a LangGraph agent with MCP tools loaded from that session.

Voice demos and blocking listen tools
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

When speech input is handled on the robot (or on the MCP server process), the blocking listen tool should not be exposed to the LangGraph agent. The demo client calls it explicitly—once per turn, before ``agent.ainvoke``—so turn-taking stays predictable: listen, then think/act. If the agent could call the listen tool itself, it might invoke it at the wrong time (for example while executing other tools, after it already started talking, or several times in one turn), which stalls the session or captures speech you did not intend as a user command. Demos implement this with ``exclude_mcp_tools`` when loading MCP tools for the agent.

Chat demos omit speech configuration on the server spawn; user text comes from the keyboard in the parent process.

Transports
----------

Each robot server is started via ``run_mcp_server()`` and accepts ``--transport``. SIC agent demos always use stdio (subprocess spawn).

.. list-table::
   :widths: 22 38 40
   :header-rows: 1

   * - Transport
     - Used by SIC demos?
     - Notes
   * - ``stdio`` (default)
     - Yes — spawned by ``mcp_stdio_connection()``.
     - stdin/stdout carry JSON-RPC only; nothing else may write to the child's stdout.
   * - ``sse``
     - No (``mcp_sse_connection()`` exists for custom clients).
     - Server listens on HTTP; connect with a URL such as ``http://127.0.0.1:8000/sse``.
   * - ``streamable-http``
     - No.
     - Same idea as SSE over HTTP; choose the transport your external MCP client expects.

.. note::
   URLs are usually plain HTTP on localhost in development (not HTTPS), unless you terminate TLS in a reverse proxy yourself.

Effect on SIC logging
---------------------

SIC's Redis client logger normally prints component and device lines to the terminal. That conflicts with stdio MCP, because stdout must carry only JSON-RPC.

``sic_framework/mcp/mcp_server.py`` configures logging for every robot server and every transport:

* ``--log-dir`` is required; the server writes SIC logs under that directory only.
* The global client log threshold is raised so Redis-forwarded lines are not printed to stdout or stderr.
* ``sic_logging.print`` is patched to append forwarded Redis messages to the log file, not the terminal.

Demos typically pass a per-session directory under ``sic_applications/logs/mcp``. When you run a server entry point by hand, pass any writable directory, for example ``--log-dir /tmp/mcp-logs``.

With stdio, the parent owns the child's stdout for JSON-RPC, so you will not see live SIC logs in the demo terminal unless you ``tail`` the log directory.

.. warning::
   The demo client and MCP server are separate SIC processes. Each may write Redis-forwarded events into its own log files. That is not necessarily two robots—only two subscribers.

Optional: standalone server or external MCP host
------------------------------------------------

You can run a robot MCP server outside the demos—for debugging tools, or for an IDE that speaks MCP. Pass ``--robot-ip``, ``--log-dir``, and optionally ``--stub``. Use ``--transport sse`` (or ``streamable-http``) only if your external client connects over HTTP; SIC demos do not use that path today.

An external host (for example Cursor) can point at the server module with stdio (command + args, including ``--log-dir``). SIC runs inside the server process; the host does not need its own ``SICApplication``.

Installation
------------

Install MCP support with the optional extra:

.. code-block:: bash

   pip install -e "social-interaction-cloud[mcp]"

Agent demos in ``sic_applications`` additionally need the ``mcp`` extra (LangChain, LangGraph, ``langchain-mcp-adapters``) and API keys in ``conf/.env`` as required by the chosen model.

NAO (reference implementation)
------------------------------

NAO is the first robot package under ``sic_framework/mcp/nao/``. It is the reference for how future robots should integrate.

Server and client
~~~~~~~~~~~~~~~~~

* Server: ``sic_framework/mcp/nao/nao_mcp_server.py`` — console entry point ``run-nao-mcp``.
* Client helpers: ``sic_framework/mcp/nao/nao_client.py`` — ``build_google_stt_conf``, ``mcp_stdio_connection``, ``nao_mcp_session_log_dir``.
* Expressions: ``nao_expressions.py`` plus shared ``expression_catalog.py``.

Voice on NAO
~~~~~~~~~~~~

The voice demo passes Google STT settings in ``SIC_NAO_STT_CONF`` when spawning the server. The server constructs ``GoogleSpeechToText`` with ``input_source=self.nao.mic``. Each loop iteration: the client calls ``listen_for_speech`` via MCP, then passes the transcript to the agent as a ``HumanMessage``; the agent may call LED, motion, and TTS tools only (``listen_for_speech`` is in ``exclude_mcp_tools``).

Chat on NAO
~~~~~~~~~~~

The chat demo spawns the same server without ``SIC_NAO_STT_CONF``. User text comes from the keyboard in the parent process.

NAO tools (overview)
~~~~~~~~~~~~~~~~~~~~

Defined in ``nao_mcp_server.py``:

* Connection: ``connect``, ``shutdown_robot`` (alias ``shutdown_nao``)
* Voice: ``listen_for_speech`` (requires ``SIC_NAO_STT_CONF`` at server startup; client use only—not exposed to the LangGraph agent)
* Eyes / LEDs: ``set_eye_color_rgb``, ``set_eye_color_name``
* Audio / speech: ``play_audio``, ``say_text``
* Motion catalog: ``get_expressions``, ``play_expression``

Stub mode (``--stub``) logs intended actions to the server log file instead of calling the robot.

Running the NAO demos
~~~~~~~~~~~~~~~~~~~~~

From ``sic_applications``:

.. code-block:: bash

   pip install -e ../social-interaction-cloud[mcp]
   pip install -e '.[mcp]'

Keyboard chat:

.. code-block:: bash

   python demos/mcp/nao/nao_mcp_chat_client.py --robot-ip <NAO_IP>

Voice (Google STT on the NAO mic via the MCP server):

.. code-block:: bash

   run-google-stt
   python demos/mcp/nao/nao_mcp_voice_client.py --robot-ip <NAO_IP>

Use ``--mcp-server-stub`` to exercise the agent without hardware. Pass ``--robot-ip`` or set ``ROBOT_IP`` / ``NAO_IP``.

Standalone NAO server:

.. code-block:: bash

   run-nao-mcp --robot-ip <NAO_IP> --log-dir /tmp/nao-mcp-logs

NAO demos
~~~~~~~~~

.. list-table::
   :widths: 35 65
   :header-rows: 1

   * - Demo
     - Role
   * - ``sic_applications/demos/mcp/nao/nao_mcp_chat_client.py``
     - Keyboard REPL; stdio MCP server; LangGraph agent calls robot tools.
   * - ``sic_applications/demos/mcp/nao/nao_mcp_voice_client.py``
     - Mic + Google STT in the MCP server; demo calls ``listen_for_speech`` then the agent.

Checklist (NAO demos today)
~~~~~~~~~~~~~~~~~~~~~~~~~~~

#. Install ``social-interaction-cloud[mcp]``.
#. Start ``run-google-stt`` before the voice demo.
#. Set ``OPENAI_API_KEY`` in ``sic_applications/conf/.env`` (or pass ``--model`` for another provider).
#. Pass ``--robot-ip`` or set ``ROBOT_IP`` / ``NAO_IP``.