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
import subprocess
try:
    import queue  # Python 3
except ImportError:
    import Queue as queue  # Python 2  # type: ignore[import-not-found]
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

        # Track background SIC service subprocesses started by this app process.
        # This prevents killing services that were already running before we started.
        self._managed_service_processes = {}
        self._managed_service_processes_lock = threading.Lock()
        self._managed_service_logs_dir = tempfile.mkdtemp(prefix="sic_managed_services_")
        
        self.shutdown_event = threading.Event()
        self.client_ip = utils.get_ip_adress()

        # Background exception handling
        self._background_exception_queue = queue.Queue()
        self._background_exception_event = threading.Event()

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
        # Python 2 compatibility: exist_ok is not supported.
        try:
            os.makedirs(path)
        except OSError:
            if not os.path.isdir(path):
                raise
        sic_logging.set_log_file(path)

    def get_app_logger(self):
        """Return the shared application logger (backward compatibility wrapper)."""
        return self.logger

    def get_shutdown_event(self):
        """Return the app-wide shutdown event (backward compatibility wrapper)."""
        return self.shutdown_event

    def start_managed_service_module(self, service_module):
        """
        Start a SIC service module in a subprocess (if this app hasn't started it already).

        Parameters
        ----------
        service_module : str
            A Python module path that can be executed via `python -m <service_module>`.
        """
        if not service_module or not isinstance(service_module, str):
            raise ValueError("service_module must be a non-empty string")

        with self._managed_service_processes_lock:
            existing = self._managed_service_processes.get(service_module)
            if existing:
                proc = existing.get("process")
                if proc is not None and proc.poll() is None:
                    return proc

            safe_name = service_module.replace(".", "_").replace("/", "_")
            stdout_path = os.path.join(self._managed_service_logs_dir, "{}_stdout.log".format(safe_name))
            stderr_path = os.path.join(self._managed_service_logs_dir, "{}_stderr.log".format(safe_name))

            stdout_fh = None
            stderr_fh = None
            proc = None
            try:
                stdout_fh = open(stdout_path, "ab", buffering=0)
                stderr_fh = open(stderr_path, "ab", buffering=0)

                # Mirror the console-script behavior (e.g. `run-face-detection=...:main`)
                # by importing `main` and calling it directly, rather than relying on
                # `if __name__ == "__main__": main()`.
                code = (
                    "import importlib; "
                    "m = importlib.import_module({mod!r}); "
                    "m.main()"
                ).format(mod=service_module)
                cmd = [sys.executable, "-c", code]
                popen_kwargs = {
                    "stdout": stdout_fh,
                    "stderr": stderr_fh,
                    "cwd": os.getcwd(),
                    "close_fds": True,
                }

                # Important: isolate the managed subprocess from the parent terminal's
                # SIGINT handling. Otherwise, when the user hits Ctrl+C, the subprocess
                # receives SIGINT too, starts shutting down early, and the parent then
                # hangs/times out while trying to stop the component it "owns".
                try:
                    proc = subprocess.Popen(
                        cmd,
                        **popen_kwargs,
                        start_new_session=True,
                    )
                except TypeError:
                    # Python2 / older Python may not support start_new_session.
                    if hasattr(os, "setsid"):
                        proc = subprocess.Popen(
                            cmd,
                            **popen_kwargs,
                            preexec_fn=os.setsid,
                        )
                    else:
                        proc = subprocess.Popen(cmd, **popen_kwargs)
            except Exception:
                # Best-effort cleanup on startup failure.
                if proc is not None:
                    try:
                        proc.kill()
                    except Exception:
                        pass
                if stdout_fh is not None:
                    try:
                        stdout_fh.close()
                    except Exception:
                        pass
                if stderr_fh is not None:
                    try:
                        stderr_fh.close()
                    except Exception:
                        pass
                raise

            self._managed_service_processes[service_module] = {
                "process": proc,
                "stdout_fh": stdout_fh,
                "stderr_fh": stderr_fh,
                "started_at": time.time(),
            }
            return proc

    def stop_managed_service_modules(self, timeout=5.0):
        """
        Stop background SIC service subprocesses started by this app process.
        Only subprocesses started by `start_managed_service_module()` are stopped.
        """
        with self._managed_service_processes_lock:
            items = list(self._managed_service_processes.items())
            # Clear early to avoid double-stops if exit handler runs multiple times.
            self._managed_service_processes = {}

        for service_module, meta in items:
            proc = meta.get("process")
            if proc is None:
                continue

            try:
                if proc.poll() is None:
                    proc.terminate()
                    start_time = time.time()
                    while proc.poll() is None and (time.time() - start_time) < timeout:
                        time.sleep(0.1)

                if proc.poll() is None:
                    proc.kill()
            except Exception:
                # Best-effort: don't fail app shutdown if service stop had issues.
                pass

            stdout_fh = meta.get("stdout_fh")
            stderr_fh = meta.get("stderr_fh")
            if stdout_fh is not None:
                try:
                    stdout_fh.close()
                except Exception:
                    pass
            if stderr_fh is not None:
                try:
                    stderr_fh.close()
                except Exception:
                    pass

    def get_redis_instance(self):
        """Return the shared Redis connection for this process."""
        self.check_health()
        if self._redis is None:
            self._redis = SICRedisConnection()
        return self._redis

    def report_background_exception(self, exception):
        """
        Report an exception that occurred in a background thread (e.g. device monitor).
        This signals the main thread to stop.
        """
        self.logger.error("Background exception reported: {}".format(exception))
        self._background_exception_queue.put(exception)
        self._background_exception_event.set()
        # Trigger shutdown immediately
        self.shutdown_event.set()

    def check_health(self):
        """
        Check if any background errors have occurred. 
        Should be called periodically by the main loop or blocking calls.
        """
        if self._background_exception_event.is_set():
            if not self._background_exception_queue.empty():
                exc = self._background_exception_queue.get()
                raise exc

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

        # First stop devices (which stops their remote component managers and their components).
        devices_to_stop = list(self._active_devices)
        self.logger.info("Stopping devices")
        for device in devices_to_stop:
            try:
                self.logger.info("Stopping device {}".format(device.name))
                for connector in device.connectors.values():
                    connector_name = getattr(connector, "component_endpoint", "unknown")
                    self.logger.info("Stopping component {} from device {}".format(connector_name, device.name))
                    connector.stop_component()
                device.stop_device()
            except Exception as e:
                self.logger.error("Error stopping device {}: {}".format(device.name, e))

        # Then stop any remaining connectors that are still alive (i.e. standalone AI services)
        connectors_to_stop = [c for c in self._active_connectors if not getattr(c, "_stopped", False)]
        self.logger.info(
            "Stopping remaining non-device components (found {count})".format(
                count=len(connectors_to_stop)
            )
        )
        for i, connector in enumerate(connectors_to_stop):
            connector_name = getattr(connector, "component_endpoint", "unknown")
            self.logger.info(
                "Stopping component {i}/{total}: {name}".format(
                    i=i + 1, total=len(connectors_to_stop), name=connector_name
                )
            )
            try:
                connector.stop_component()
            except Exception as e:
                self.logger.warning(
                    "Warning: Error stopping component {name}: {e}".format(
                        name=connector_name, e=e
                    )
                )

        self.logger.info("Stopping managed SIC service subprocesses")
        self.stop_managed_service_modules()

        self.logger.info("All components stopped, stopping logging thread")
        
        # Stop the SICClientLog thread before closing Redis
        sic_logging.SIC_CLIENT_LOG.stop()
        
        self.logger.info("Shutting down Redis connection")
        if self._redis is not None:
            self._redis.close()
            self._redis = None

        try:
            sys.exit(0)
        except Exception as e:
            pass

    def register_exit_handler(self):
        """Idempotently register signal and atexit shutdown handlers."""
        if self._shutdown_handler_registered:
            return
        self._shutdown_handler_registered = True
        atexit.register(self.exit_handler)
        signal.signal(signal.SIGINT, self.exit_handler)
        signal.signal(signal.SIGTERM, self.exit_handler)
