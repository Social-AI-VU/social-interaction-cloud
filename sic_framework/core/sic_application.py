"""
Boilerplate setup for SIC applications.
"""

from sic_framework.core import utils
from sic_framework.core import sic_logging
from dotenv import load_dotenv
import signal, sys, atexit
import tempfile
import os
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

# Create the application-wide Redis instance
_app_redis = None

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
    print("Running atexit cleanup, closing Redis connection...")
    if _app_redis is not None:
        _app_redis.close()
        _app_redis = None

def handler(signum, frame):
    print("signal interrupt received, exiting...")
    sys.exit(0)

atexit.register(cleanup)
signal.signal(signal.SIGINT, handler)