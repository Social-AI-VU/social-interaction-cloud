"""
sic_logging.py

This module contains the SICLogging class, which is used to log messages to the Redis log channel and a local logfile.
"""

from __future__ import print_function

import io
import logging
import re
import threading
from datetime import datetime
import os

from . import utils
from .message_python2 import SICMessage

ANSI_CODE_REGEX = re.compile(r'\033\[[0-9;]*m')

# loglevel interpretation, mostly follows python's defaults
CRITICAL = 50
ERROR = 40
WARNING = 30
INFO = 20 
DEBUG = 10 
NOTSET = 0


def get_log_channel(client_id=""):
    """
    Get the global log channel. All components on any device should log to this channel.
    """
    return "sic:logging:{client_id}".format(client_id=client_id)


class SICLogMessage(SICMessage):
    def __init__(self, msg, client_id=""):
        """
        A wrapper for log messages to be sent over the SIC SICRedisConnection pubsub framework.
        :param msg: The log message to send to the user
        """
        self.msg = msg
        self.client_id = client_id
        super(SICLogMessage, self).__init__()


class SICRemoteError(Exception):
    """An exception indicating the error happened on a remote device"""


class SICClientLog(object):
    """
    A class to subscribe to a Redis log channel and write all log messages to a logfile.

    Pseudo singleton object. Does nothing when this file is executed during the import, but can subscribe to the log
    channel for the user with subscribe_to_redis_log once.

    :param redis: The Redis instance to use for logging.
    :type redis: SICRedisConnection
    :param logfile: The file path to write the log to.
    :type logfile: str
    """
    def __init__(self):
        self.redis = None
        self.running = False
        self.logfile = None
        self.log_dir = None
        self.write_to_logfile = False
        self.lock = threading.Lock()
        self.threshold = DEBUG
        self.callback_thread = None

    def subscribe_to_redis_log(self, client_id=""):
        """
        Subscribe to the Redis log channel and display any messages on the terminal. 
        This function may be called multiple times but will only subscribe once.

        :return: None
        """
        with self.lock:  # Ensure thread-safe access
            if not self.running:
                self.running = True
                self.callback_thread = self.redis.register_message_handler(
                    get_log_channel(client_id), self._handle_redis_log_message, name="SICClientLog"
                )

    def stop(self):
        """
        Stop the logging and unregister the callback thread.
        """
        with self.lock:  # Ensure thread-safe access
            if self.running:
                self.running = False
                # Unregister the callback thread from Redis
                if self.callback_thread and self.redis:
                    try:
                        self.redis.unregister_callback(self.callback_thread)
                        self.callback_thread = None
                    except Exception:
                        # Ignore errors during shutdown (Redis might already be closed)
                        pass
            if self.logfile:
                self.logfile.close()
                self.logfile = None

    def set_log_file_path(self, path):
        """
        Set the path to the log file.

        :param path: The path to the log file.
        :type path: str
        """
        with self.lock:
            self.log_dir = os.path.normpath(path)
            if not os.path.exists(self.log_dir):
                os.makedirs(self.log_dir)
            if self.logfile is not None:
                self.logfile.close()
                self.logfile = None


    def _handle_redis_log_message(self, message):
        """
        Handle a message sent on the Redis stream.

        If it surpasses the threshold, it will be printed to the terminal and written to the logfile (if enabled).

        :param message: The message to handle.
        :type message: SICLogMessage
        """
        # default to INFO level if not set
        level = getattr(message, 'level', logging.INFO)
        # check if the level is greater than or equal to the threshold
        if level >= self.threshold:
            # outputs to terminal
            try:    
                print(message.msg, end="\n")
            except BrokenPipeError:
                pass

            if self.write_to_logfile:
                # writes to logfile
                self._write_to_logfile(message.msg)
    
    def _write_to_logfile(self, message):
        """
        Write a message to the logfile.

        :param message: The message to write to the logfile.
        :type message: str
        """
        acquired = self.lock.acquire(timeout=0.5)
        if not acquired:
            return
        try:
            if self.log_dir is None:
                # on remote devices the log_dir is set to None. We don't want to write to a logfile on remote devices
                return
            if self.logfile is None:
                if not os.path.exists(self.log_dir):
                    os.makedirs(self.log_dir)
                current_date = datetime.now().strftime("%Y-%m-%d")
                log_path = os.path.join(self.log_dir, "sic_{current_date}.log".format(current_date=current_date))
                self.logfile = open(log_path, "a")

            # strip ANSI codes before writing to logfile
            clean_message = ANSI_CODE_REGEX.sub("", message)

            # add timestamp to the log message
            timestamp = datetime.now().strftime("%H:%M:%S")
            clean_message = "[{timestamp}] {clean_message}".format(timestamp=timestamp, clean_message=clean_message)
            if clean_message[-1] != "\n":
                clean_message += "\n"

            # write to logfile
            self.logfile.write(clean_message)
            self.logfile.flush()
        finally:
            self.lock.release()

class SICRedisLogHandler(logging.Handler):
    """
    Facilities to log to Redis as a file-like object, to integrate with standard python logging facilities.

    :param redis: The Redis instance to use for logging.
    :type redis: SICRedisConnection
    :param client_id: The client id of the device that is logging
    :type client_id: str
    """
    def __init__(self, redis, client_id):
        super(SICRedisLogHandler, self).__init__()
        self.redis = redis
        self.client_id = client_id
        self.logging_channel = get_log_channel(client_id)

    def emit(self, record):
        """
        Emit a log message to the Redis log channel.

        :param record: The log record to emit.
        :type record: logging.LogRecord
        """
        try:
            if self.redis.stopping:
                return # silently ignore messages if the application is stopping

            # Get the formatted message
            msg = self.format(record)
            
            # Create the log message with client_id if it exists
            log_message = SICLogMessage(msg)

            # If additional client id is provided (as with the ComponentManager), use it to send the log message to the correct channel
            if hasattr(record, 'client_id') and self.client_id == "":
                log_message.client_id = record.client_id
                log_channel = get_log_channel(log_message.client_id)
            else:
                log_channel = self.logging_channel

            log_message.level = record.levelno

            # Send over Redis
            self.redis.send_message(log_channel, log_message)
        except Exception:
            if not self.redis.stopping:
                self.handleError(record)

    def readable(self):
        """
        Check if the stream is readable.

        :return: False
        :rtype: bool
        """
        return False

    def writable(self):
        """
        Check if the stream is writable.

        :return: True
        :rtype: bool
        """
        return True

    def write(self, msg):
        """
        Write a message to the Redis log channel.

        :param msg: The message to write to the Redis log channel.
        :type msg: str
        """
        # only send logs to redis if a redis instance is associated with this logger
        if self.redis != None:
            message = SICLogMessage(msg)
            self.redis.send_message(self.logging_channel, message)

    def flush(self):
        """
        Flush the stream.
        """
        return

class SICLogFormatter(logging.Formatter):
    """
    A formatter for SIC log messages.
    """
    # Define ANSI escape codes for colors
    LOG_COLORS = {
        logging.DEBUG: "\033[92m",  # Green
        logging.INFO: "\033[94m",   # Blue
        logging.WARNING: "\033[93m",  # Yellow
        logging.ERROR: "\033[91m",  # Deep Red
        logging.CRITICAL: "\033[101m\033[97m",  # Bright Red (White on Red Background)
    }
    RESET_COLOR = "\033[0m"  # Reset color

    def format(self, record):
        """
        Format a log message.

        :param record: The log record to format.
        :type record: logging.LogRecord
        """
        # Get the color for the current log level
        color = self.LOG_COLORS.get(record.levelno, self.RESET_COLOR)

        # Create the prefix part
        # Highlight and bold "SICApplication" in the logger name if present
        name = record.name
        pad_amount = 45
        if "SICApplication" in name:
            pad_amount = 58
            # ANSI escape codes: bold (\033[1m), yellow (\033[93m), reset (\033[0m)
            highlighted = "\033[1m\033[93mSICApplication\033[0m"
            name = name.replace("SICApplication", highlighted)
        name_ip = "[{name} {ip}]".format(
            name=name,
            ip=utils.get_ip_adress()
        )
        name_ip_padded = name_ip.ljust(pad_amount, '-')
        prefix = "{name_ip_padded}{color}{record_level}{reset_color}: ".format(name_ip_padded=name_ip_padded, color=color, record_level=record.levelname, reset_color=self.RESET_COLOR)

        # Split message into lines and handle each line
        try:
            message_lines = str(record.getMessage()).splitlines()
        except Exception as e:
            message_lines = ["ERROR: Could not get message from record: {}".format(record), "Exception: {e}".format(e=e)]
        if not message_lines:
            return prefix

        # Format first line with full prefix
        formatted_lines = ["{prefix}{message_lines}".format(prefix=prefix, message_lines=message_lines[0])]

        # For subsequent lines, indent to align with first line's content
        if len(message_lines) > 1:
            indent = ' ' * len(prefix)
            formatted_lines.extend("{indent}{line}".format(indent=indent, line=line.strip()) for line in message_lines[1:])

        # If an exception was attached (e.g., logger.exception), append formatted exception text
        if record.exc_info:
            try:
                exc_text = self.formatException(record.exc_info)
            except Exception:
                exc_text = None
            if exc_text:
                indent = ' ' * len(prefix)
                for line in str(exc_text).splitlines():
                    formatted_lines.append("{indent}{line}".format(indent=indent, line=line))

        # Join all lines with newlines
        return '\n'.join(formatted_lines)

    def formatException(self, exec_info):
        """
        Prepend every exception with a | to indicate it is not local.

        :param exec_info: The exception information.
        :type exec_info: tuple
        :return: The formatted exception.
        :rtype: str
        """
        text = super(SICLogFormatter, self).formatException(exec_info)
        text = "| " + text.replace("\n", "\n| ")
        text += "\n| NOTE: Exception occurred in SIC framework, not application"
        return text


def get_sic_logger(name="", client_id="", redis=None, client_logger=False):
    """
    Set up logging to the log output channel to be able to report messages to users.

    :param name: A readable and identifiable name to indicate to the user where the log originated
    :type name: str
    :param client_id: The client id of the device that is logging
    :type client_id: str
    :param redis: The SICRedisConnection object
    :type redis: SICRedisConnection
    :return: The logger.
    :rtype: logging.Logger
    """
    # logging initialisation
    # Always set logger to DEBUG so it logs everything - SICClientLog will filter what to display
    logger = logging.Logger(name)
    logger.setLevel(DEBUG)
    log_format = SICLogFormatter()

    handler_redis = SICRedisLogHandler(redis, client_id)
    handler_redis.setFormatter(log_format)
    logger.addHandler(handler_redis)

    if client_logger:
        SIC_CLIENT_LOG.redis = redis
        SIC_CLIENT_LOG.subscribe_to_redis_log(client_id)

    return logger

# pseudo singleton object. Does nothing when this file is executed during the import, but can subscribe to the log
# channel for the user with subscribe_to_redis_log once
SIC_CLIENT_LOG = SICClientLog()

def set_log_level(level):
    """
    Set the log level threshold for SICClientLog.
    This filters which messages are displayed/written, but all messages are still logged.
    
    :param level: The log level threshold (DEBUG, INFO, WARNING, ERROR, CRITICAL)
    :type level: int
    """
    SIC_CLIENT_LOG.threshold = level

def set_log_file(path):
    SIC_CLIENT_LOG.write_to_logfile = True
    SIC_CLIENT_LOG.set_log_file_path(path)