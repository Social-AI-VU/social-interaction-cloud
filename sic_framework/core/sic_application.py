"""
Application infrastructure and lifecycle management for SIC (Social Interaction Cloud) applications.

Provides essential boilerplate setup and infrastructure for SIC applications, including:
- Logging setup and configuration
- Process-wide Redis connection management
- Graceful shutdown handling
- Connector lifecycle management
- Application-wide state management
"""

from sic_framework.core import utils
from sic_framework.core import sic_logging
import signal, sys, atexit, threading
import tempfile
import os
import weakref
import time
from sic_framework.core.sic_redis import SICRedisConnection

# Initialize logging
# can be set to DEBUG, INFO, WARNING, ERROR, CRITICAL
sic_logging.set_log_level(sic_logging.DEBUG)

# Global state
_app_redis = None
_cleanup_in_progress = False
_shutdown_event = None
_active_connectors = weakref.WeakSet()
_app_logger = None
_shutdown_handler_registered = False

def register_connector(connector):
    """
    Register a connector to be shutdown when the application shuts down.
    """
    global _active_connectors
    _active_connectors.add(connector)

def set_log_level(level):   
    """
    Set the log level for the application.

    :param level: The log level to set.
    :type level: 
    """
    sic_logging.set_log_level(level)

def set_log_file(path):
    """
    Set the log file path for the application.

    Must be a valid full path to a directory.

    :param path: The log file path to set.
    :type path: str
    """
    # Create the directory if it doesn't exist (parent directories too)
    os.makedirs(path, exist_ok=True)
    sic_logging.set_log_file(path)

def get_shutdown_event():
    """
    Get or create the application-wide shutdown event.

    To be used inside main thread of the application for loops.
    """
    global _shutdown_event
    if _shutdown_event is None:
        _shutdown_event = threading.Event()
    return _shutdown_event

def get_app_logger():
    """
    Get or create the application-wide logger.

    To be used inside main thread of the application. Sets client_logger=True so that the Redis log channel
    is subscribed to. Causes log messages to be printed and written to the logfile.
    """
    global _app_logger
    if _app_logger is None:
        _app_logger = sic_logging.get_sic_logger("SICApplication", client_id=utils.get_ip_adress(), redis=get_redis_instance(), client_logger=True)
    return _app_logger

def get_redis_instance():
    """
    Get or create the application-wide Redis instance.

    Shared by Connectors and DeviceManagers.
    """
    global _app_redis
    if _app_redis is None:
        _app_redis = SICRedisConnection()
    return _app_redis


def exit_handler(signum=None, frame=None):
    """
    Signal handler for graceful shutdown.

    Stops all connectors and closes the Redis connection.
    """
    global _cleanup_in_progress, _shutdown_event, _app_redis 
    
    _app_logger = get_app_logger()
    
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
            _app_logger.error("Error stopping connector {name}: {e}".format(name=connector.component_endpoint, e=e))

    _app_logger.info("Closing redis connection")
    if _app_redis is not None:
        _app_redis.close()
        _app_redis = None

    # Check if we're in the main thread
    if hasattr(threading, "main_thread"):
        is_main_thread = (threading.current_thread() == threading.main_thread())
    else:
        # Python 2 fallback
        is_main_thread = (threading.current_thread().name == "MainThread")

    # Only exit if we're in the main thread
    if is_main_thread:
        _app_logger.info("Exiting main thread")
        sys.exit(0)

def register_exit_handler():
    """
    Register the exit handler.
    """
    global _shutdown_handler_registered
    if _shutdown_handler_registered:
        return
    _shutdown_handler_registered = True
    atexit.register(exit_handler)
    signal.signal(signal.SIGINT, exit_handler)
    signal.signal(signal.SIGTERM, exit_handler)