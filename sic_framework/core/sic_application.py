"""
Boilerplate setup for SIC applications.
"""

from sic_framework.core import utils
from sic_framework.core import sic_logging
from dotenv import load_dotenv
import signal, sys, atexit, threading
import tempfile
import os
import weakref
import time
from sic_framework.core.sic_redis import SICRedis

# Initialize logging
# can be set to DEBUG, INFO, WARNING, ERROR, CRITICAL
sic_logging.set_log_level(sic_logging.DEBUG)

# Get system's temp directory and create SIC-specific log directory
LOG_PATH = os.path.join(tempfile.gettempdir(), "sic", "logs")
# Create the directory if it doesn't exist (parent directories too)
os.makedirs(LOG_PATH, exist_ok=True)

# sic logging will automatically create the log directory if it doesn't exist
sic_logging.set_log_file_path(LOG_PATH)

# Global state
_app_redis = None
_cleanup_in_progress = False
_shutdown_event = None
_active_connectors = weakref.WeakSet()
_app_logger = None

def register_connector(connector):
    """Register a connector to be shutdown when the application shuts down."""
    global _active_connectors
    _active_connectors.add(connector)

def get_shutdown_event():
    """
    Get or create the application-wide shutdown event.
    """
    global _shutdown_event
    if _shutdown_event is None:
        _shutdown_event = threading.Event()
    return _shutdown_event

def get_app_logger():
    """
    Get or create the application-wide logger.
    """
    global _app_logger
    if _app_logger is None:
        _app_logger = sic_logging.get_sic_logger("SICApplication", client_id=utils.get_ip_adress())
    return _app_logger

def get_redis_instance():
    """
    Get or create the application-wide Redis instance.
    """
    global _app_redis
    if _app_redis is None:
        _app_redis = SICRedis()
    return _app_redis


def exit_handler(signum=None, frame=None):
    """
    Signal handler for graceful shutdown.
    """
    global _cleanup_in_progress, _shutdown_event, _app_redis, _app_logger
    
    if _cleanup_in_progress:
        return  # Prevent multiple signal handling
    _cleanup_in_progress = True
        
    _app_logger.info("signal interrupt received, exiting...")
    
    # Signal the shutdown event if it exists
    if _shutdown_event is not None:
        _app_logger.info("Setting shutdown event")
        _shutdown_event.set()

    _app_logger.info("Stopping connectors")
    # Stop connectors (each connector signals to respective CM to stop the component)
    connectors_to_stop = list(_active_connectors)
    for connector in connectors_to_stop:
        try:
            connector.stop_component()
        except Exception as e:
            _app_logger.info(f"Error stopping connector: {e}")

    _app_logger.info("Closing redis connection")
    if _app_redis is not None:
        _app_redis.close()
        _app_redis = None

    # Only exit if we're in the main thread
    if threading.current_thread() is threading.main_thread():
        _app_logger.info("Exiting main thread")
        sys.exit(0)

atexit.register(exit_handler)
signal.signal(signal.SIGINT, exit_handler)
signal.signal(signal.SIGTERM, exit_handler)