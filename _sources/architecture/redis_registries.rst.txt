Redis registries (multi-user and shared Redis)
==============================================

SIC uses Redis both as a **pub/sub message broker** and as a small **metadata store** for two Redis hashes. Together they support **multiple clients** talking to the **same Redis instance** without accidentally sharing physical hardware or confusing one client’s component pipeline with another’s.

Purpose
-------

When several users or processes share one Redis host (for example a lab server), SIC must answer:

1. **Who may use this robot or device?** A **device reservation** maps a stable device identifier (typically the device IP used when constructing a device manager) to the **client id** of the machine that reserved it. That gives **exclusive use** of that device key for one client at a time, which avoids the failure mode where two scripts both drive the same robot.

2. **Which client owns which logical data stream?** A **data stream** entry ties a **stream id** (the component’s ``component_channel``) to **which client** started the component, which **component endpoint** it is, and which **input channel** feeds it. That keeps pipelines **traceable** and distinct when many clients run components against the same broker.

.. note::
   Many tutorials assume **one developer** and **Redis on localhost**. In that setup you may never hit reservation conflicts, and the registries still exist but often hold only your client’s entries. The same code paths are used when you point ``DB_IP`` at a **shared** Redis server.

Redis keys and storage model
----------------------------

``SICRedisConnection`` in ``sic_framework/core/sic_redis.py`` defines two hash names:

.. list-table::
   :widths: 30 70
   :header-rows: 1

   * - Redis key
     - Role
   * - ``cache:reservations``
     - Field: **device id** (string, e.g. device IP). Value: **client id** (string).
   * - ``cache:data_streams``
     - Field: **data stream id** (string, the component channel id). Value: **JSON object** (see below).

The API surface on ``SICRedisConnection`` includes:

* Reservations: ``get_reservation_map``, ``get_reservation``, ``set_reservation``, ``unset_reservation``
* Data streams: ``get_data_stream_map``, ``get_data_stream``, ``set_data_stream``, ``unset_data_stream``
* Cleanup: ``remove_client``, ``ping_client``

Device reservations
-------------------

**When reservations are set**

``SICDeviceManager`` (``sic_framework/devices/device.py``) calls ``set_reservation()`` during construction, after the Redis connection and client id are available.

**Localhost exception**

If the device IP is ``localhost`` or ``127.0.0.1``, **no reservation is written**. That keeps local-only workflows simple; it also means the **exclusive-device** guarantee does not apply to that key in the same way as for a distinct LAN IP.

**Conflict behavior**

For non-localhost devices, the manager reads any existing mapping with ``get_reservation(device_ip)``:

* If **no** reservation exists, it calls ``set_reservation(device_ip, client_id)``. A return value other than ``1`` raises ``DeviceReservationError``.
* If the device is **already reserved by this client**, it returns without error.
* If another client holds the reservation, the code **pings** that client with ``ping_client(other_client_id)``. ``ping_client`` returns true if a Redis pub/sub channel exists whose name matches the logging subscription pattern for that client (implementation in ``sic_redis.py``).
* If the other client **does not** appear connected, ``remove_client(other_client_id)`` clears **all** of that client’s reservations and data stream entries, then this client proceeds to reserve.
* If the other client **does** appear connected, ``DeviceReservationError`` is raised (the familiar “device already reserved” case).

**Stale state**

``remove_client`` walks the reservation hash and the data stream hash and deletes any entry belonging to the given ``client_id``. It is used when a client disconnects without cleaning up, or when the stale-holder check above decides the old client is gone.

Data streams
------------

After a component starts successfully, the device-side ``SICComponentManager`` (``sic_framework/core/component_manager_python2.py``) registers the stream with ``set_data_stream(component_channel, data_stream_info)`` where ``data_stream_info`` is a dict containing at least:

* ``component_endpoint`` — which component this is
* ``input_channel`` — where its input is wired
* ``client_id`` — which client owns this pipeline

When ``stop_component`` runs, the manager calls ``unset_data_stream(component.component_channel)`` so the registry matches running components.

Together with pub/sub channel names derived from these ids, this makes it possible to see **who** registered **which** stream on a shared broker and to tear down **all** of one client’s metadata via ``remove_client``.

Operational expectations
------------------------

* **Solo + local Redis:** Typical getting-started flows use a single ``DB_IP`` and one client; registries may contain only one client’s keys. Reservation conflicts are uncommon unless you run multiple scripts against the same remote device IP.
* **Shared Redis:** Point multiple machines at the same ``DB_IP`` / ``DB_PORT`` / ``DB_PASS``. Reservations and data stream entries then matter for **correct routing and exclusivity**; misconfiguration can look like reservation errors or confusing stream ownership.

For Redis connectivity and passwords, see :doc:`../faq/comprehensive_faq` (Redis sections). For the pub/sub side of Redis, see :doc:`architecture/message_system`.
