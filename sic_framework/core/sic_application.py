"""
SIC application runtime: process-wide lifecycle and infrastructure.

Provides a singleton for:
- Centralized logging setup and configuration
- Shared Redis connection management
- Graceful shutdown (signal and atexit) with device and connector cleanup
- Registration of connectors/devices and an app-wide shutdown event
"""

from sic_framework.core import utils
from sic_framework.core import sic_logging
import signal, sys, atexit, threading
import tempfile
import os
import weakref
import time
from sic_framework.core.sic_redis import SICRedisConnection

class SICApplication(object):
    """
    Process-wide singleton for SIC app infrastructure.

    Responsibilities:
    - Expose a shared Redis connection and app logger
    - Register and gracefully stop connectors on exit
    - Provide an application shutdown event for main loops
    - Auto-register a SIGINT/SIGTERM/atexit handler on first creation
    """

    _instance = None
    _instance_lock = threading.Lock()

    def __new__(cls, *args, **kwargs):
        """Return the single instance (thread-safe lazy init)."""
        if cls._instance is not None:
            return cls._instance
        with cls._instance_lock:
            if cls._instance is None:
                cls._instance = super(SICApplication, cls).__new__(cls)
        return cls._instance

    def __init__(self):
        """Initialize runtime state and register exit handler once."""
        if getattr(self, "_initialized", False):
            return

        # Logging defaults (can be changed via set_log_level / set_log_file)
        sic_logging.set_log_level(sic_logging.DEBUG)

        # Runtime state
        self._redis = None
        self._cleanup_in_progress = False
        self._shutdown_event = None
        self._active_connectors = weakref.WeakSet()
        self._active_devices = weakref.WeakSet()
        self._app_logger = None
        self._shutdown_handler_registered = False

        # Automatically register exit handler once per process
        self.register_exit_handler()

        self._initialized = True

    # ------------ Public API (instance methods) ------------
    def register_connector(self, connector):
        """Track a connector for cleanup during shutdown."""
        self._active_connectors.add(connector)

    def register_device(self, device):
        """Track a device manager."""
        self._active_devices.add(device)

    def set_log_level(self, level):
        """Set global log level for the application runtime."""
        sic_logging.set_log_level(level)

    def set_log_file(self, path):
        """Write logs to directory at ``path`` (created if missing)."""
        os.makedirs(path, exist_ok=True)
        sic_logging.set_log_file(path)

    def get_shutdown_event(self):
        """Return an app-wide ``threading.Event`` to control main loops."""
        if self._shutdown_event is None:
            self._shutdown_event = threading.Event()
        return self._shutdown_event

    def get_app_logger(self):
        """Return the shared application logger (client_logger=True)."""
        if self._app_logger is None:
            self._app_logger = sic_logging.get_sic_logger(
                "SICApplication",
                client_id=utils.get_ip_adress(),
                redis=self.get_redis_instance(),
                client_logger=True,
            )
        return self._app_logger

    def get_redis_instance(self):
        """Return the shared Redis connection for this process."""
        if self._redis is None:
            self._redis = SICRedisConnection()
        return self._redis

    def shutdown(self):
        """Gracefully stop connectors and close Redis, then exit main thread."""
        self.exit_handler()

    def exit_handler(self, signum=None, frame=None):
        """Gracefully stop connectors and close Redis, then exit main thread.

        Called on SIGINT/SIGTERM and at process exit (atexit).
        """
        if self._cleanup_in_progress:
            return
        self._cleanup_in_progress = True

        app_logger = self.get_app_logger()
        app_logger.info("signal interrupt received, exiting...")

        if self._shutdown_event is not None:
            app_logger.info("Setting shutdown event")
            self._shutdown_event.set()

        app_logger.info("Stopping devices")
        # devices_to_stop = list(self._active_devices)
        # for device in devices_to_stop:
        #     try:
        #         device.stop_device()
        #     except Exception as e:
        #         app_logger.error("Error stopping device {name}: {e}".format(name=device.name, e=e))

        app_logger.info("Stopping connectors")
        connectors_to_stop = list(self._active_connectors)
        for connector in connectors_to_stop:
            # Skip if this connector belongs to a device we already stopped
            # if any(connector in device._connectors for device in devices_to_stop):
            #     app_logger.debug("Skipping connector {name} as it belongs to a device we already stopped".format(name=connector.component_endpoint))
            #     continue
                
            try:
                connector.stop_component()
            except Exception as e:
                app_logger.error(
                    "Error stopping connector {name}: {e}".format(
                        name=getattr(connector, "component_endpoint", "unknown"), e=e
                    )
                )

        app_logger.info("Closing redis connection")
        if self._redis is not None:
            self._redis.close()
            self._redis = None

    def register_exit_handler(self):
        """Idempotently register signal and atexit shutdown handlers."""
        if self._shutdown_handler_registered:
            return
        self._shutdown_handler_registered = True
        atexit.register(self.exit_handler)
        signal.signal(signal.SIGINT, self.exit_handler)
        signal.signal(signal.SIGTERM, self.exit_handler)

