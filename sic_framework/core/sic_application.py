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

# Create the process-wide Redis instance
_process_redis = None

def get_redis_instance(parent_name=None):
    """
    Get or create the process-wide Redis instance.
    """
    global _process_redis
    if _process_redis is None:
        _process_redis = SICRedis(parent_name=parent_name)
    return _process_redis

# load in any environment variables from the .env file
load_dotenv("../.env")

# register cleanup and signal handler
def cleanup():
    print("Running atexit cleanup, closing Redis connection...")
    if _process_redis is not None:
        _process_redis.close()
        _process_redis = None

def handler(signum, frame):
    print("SIGINT received!")
    sys.exit(0)

atexit.register(cleanup)
signal.signal(signal.SIGINT, handler)