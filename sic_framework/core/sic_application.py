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
        """
        Initialize runtime state and register exit handler once.
        """
        # Only initialize once (singleton pattern)
        if getattr(self, "_initialized", False):
            return

        # Runtime state
        self._redis = None
        self._cleanup_in_progress = False
        self._active_connectors = weakref.WeakSet()
        self._active_devices = weakref.WeakSet()
        self._shutdown_handler_registered = False
        
        self.shutdown_event = threading.Event()
        self.client_ip = utils.get_ip_adress()

        # Initialize logger (will be available immediately)
        self.logger = sic_logging.get_sic_logger(
            "SICApplication",
            client_id=utils.get_ip_adress(),
            redis=self.get_redis_instance(),
            client_logger=True,
        )

        # Automatically register exit handler once per process
        self.register_exit_handler()

        self._initialized = True

    # ------------ Public API (instance methods) ------------
    def register_connector(self, connector):
        """Track a connector for cleanup during shutdown."""
        # don't register connectors if cleanup is in progress (maybe there was an error during startup)
        if self._cleanup_in_progress:
            return
        self._active_connectors.add(connector)

    def register_device(self, device):
        """Track a device manager."""
        # don't register devices if cleanup is in progress (maybe there was an error during startup)
        if self._cleanup_in_progress:
            return
        self._active_devices.add(device)

    def set_log_level(self, level):
        """Set global log level for the application runtime."""
        sic_logging.set_log_level(level)

    def set_log_file(self, path):
        """Write logs to directory at ``path`` (created if missing)."""
        os.makedirs(path, exist_ok=True)
        sic_logging.set_log_file(path)

    def get_app_logger(self):
        """Return the shared application logger (backward compatibility wrapper)."""
        return self.logger

    def get_shutdown_event(self):
        """Return the app-wide shutdown event (backward compatibility wrapper)."""
        return self.shutdown_event

    def get_redis_instance(self):
        """Return the shared Redis connection for this process."""
        if self._redis is None:
            self._redis = SICRedisConnection()
        return self._redis

    def setup(self):
        """
        Hook for application-specific setup (devices, connectors, etc.).
        
        Override this method in subclasses to initialize your application
        components before the main loop runs.
        """
        pass

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

        self.logger.info("signal interrupt received, exiting...")

        if self.shutdown_event is not None:
            self.logger.info("Setting shutdown event")
            self.shutdown_event.set()

        self.logger.info("Stopping devices")
        # devices_to_stop = list(self._active_devices)
        # for device in devices_to_stop:
        #     try:
        #         device.stop_device()
        #     except Exception as e:
        #         self.logger.error("Error stopping device {name}: {e}".format(name=device.name, e=e))

        self.logger.info("Stopping components (found {count} components)".format(count=len(self._active_connectors)))
        connectors_to_stop = list(self._active_connectors)
        for i, connector in enumerate(connectors_to_stop):
            # Skip if this connector belongs to a device we already stopped
            # if any(connector in device._connectors for device in devices_to_stop):
            #     self.logger.debug("Skipping connector {name} as it belongs to a device we already stopped".format(name=connector.component_endpoint))
            #     continue
            
            connector_name = getattr(connector, "component_endpoint", "unknown")
            self.logger.info("Stopping component {i}/{total}: {name}".format(i=i+1, total=len(connectors_to_stop), name=connector_name))
            try:
                connector.stop_component()
            except Exception as e:
                self.logger.warning(
                    "Warning: Error stopping component {name}: {e}".format(
                        name=getattr(connector, "component_endpoint", "unknown"), e=e
                    )
                )
                # import traceback
                # traceback.print_exc()

        self.logger.info("All components stopped, stopping logging thread")
        
        # Stop the SICClientLog thread before closing Redis
        sic_logging.SIC_CLIENT_LOG.stop()
        
        self.logger.info("Shutting down Redis connection")
        if self._redis is not None:
            self._redis.close()
            self._redis = None

        sys.exit(0)

    def register_exit_handler(self):
        """Idempotently register signal and atexit shutdown handlers."""
        if self._shutdown_handler_registered:
            return
        self._shutdown_handler_registered = True
        atexit.register(self.exit_handler)
        signal.signal(signal.SIGINT, self.exit_handler)
        signal.signal(signal.SIGTERM, self.exit_handler)

