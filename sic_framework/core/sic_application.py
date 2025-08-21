"""
Boilerplate setup for SIC applications.
"""

from sic_framework.core import utils
from sic_framework.core import sic_logging
from dotenv import load_dotenv
import signal, sys, atexit, threading
import tempfile
import os
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

def get_redis_instance():
    """
    Get or create the application-wide Redis instance.
    """
    global _app_redis
    if _app_redis is None:
        _app_redis = SICRedis()
    return _app_redis

# load in any environment variables from the .env file
load_dotenv("../.env")

# register cleanup and signal handler
def cleanup():
    """
    Cleanup function to stop Redis and other resources.
    """
    global _app_redis, _cleanup_in_progress
    if _cleanup_in_progress:
        return
    _cleanup_in_progress = True
    
    try:
        print("Closing Redis connection...")
        if _app_redis is not None:
            _app_redis.close()
            _app_redis = None
    except Exception as e:
        print(f"Error during cleanup: {e}")
    finally:
        _cleanup_in_progress = False

def handler(signum, frame):
    """
    Signal handler for graceful shutdown.
    """
    if _cleanup_in_progress:
        return  # Prevent multiple signal handling
        
    print("signal interrupt received, exiting...")

    # Only exit if we're in the main thread
    if threading.current_thread() is threading.main_thread():
        sys.exit(0)

atexit.register(cleanup)
signal.signal(signal.SIGINT, handler)
signal.signal(signal.SIGTERM, handler)