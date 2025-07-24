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

from . import utils
from .message_python2 import SICMessage
from .sic_redis import SICRedis

ANSI_CODE_REGEX = re.compile(r'\033\[[0-9;]*m')

# loglevel interpretation, mostly follows python's defaults
CRITICAL = 50
ERROR = 40
WARNING = 30
INFO = 20  # service dependent sparse information
DEBUG = 10  # service dependent verbose information
NOTSET = 0


def get_log_channel(client_id=""):
    """
    Get the global log channel. All components on any device should log to this channel.
    """
    return "sic:logging:{client_id}".format(client_id=client_id)


class SICLogMessage(SICMessage):
    def __init__(self, msg, client_id=""):
        """
        A wrapper for log messages to be sent over the SICRedis pubsub framework.
        :param msg: The log message to send to the user
        """
        self.msg = msg
        self.client_id = None
        super(SICLogMessage, self).__init__()


class SICRemoteError(Exception):
    """An exception indicating the error happened on a remote device"""


class SICCommonLog(object):
    """
    A class to subscribe to a Redis log channel and write all log messages to a logfile.

    Pseudo singleton object. Does nothing when this file is executed during the import, but can subscribe to the log
    channel for the user with subscribe_to_redis_log once.

    :param redis: The Redis instance to use for logging.
    :type redis: SICRedis
    :param logfile: The file path to write the log to.
    :type logfile: str
    """
    def __init__(self):
        self.redis = None
        self.running = False
        
        # Create log filename with current date
        current_date = datetime.now().strftime("%Y-%m-%d")
        self.logfile = open("sic_{date}.log".format(date=current_date), "a")
        
        self.lock = threading.Lock()

    def subscribe_to_redis_log(self, client_id=""):
        """
        Subscribe to the Redis log channel and display any messages on the terminal. 
        This function may be called multiple times but will only subscribe once.

        :return: None
        """
        with self.lock:  # Ensure thread-safe access
            if not self.running:
                self.running = True
                self.redis = SICRedis(parent_name="SICCommonLog")
                self.redis.register_message_handler(
                    get_log_channel(client_id), self._handle_redis_log_message
                )

    def _handle_redis_log_message(self, message):
        """
        Handle a message sent on a debug stream. Currently it's just printed to the terminal.

        :param message: The message to handle.
        :type message: SICLogMessage
        """
        # outputs to terminal
        print(message.msg, end="\n")

        # writes to logfile
        self._write_to_logfile(message.msg)
    
    def _write_to_logfile(self, message):
        """
        Write a message to the logfile.

        :param message: The message to write to the logfile.
        :type message: str
        """
        with self.lock:
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


    def stop(self):
        """
        Stop the logging.
        """
        with self.lock:  # Ensure thread-safe access
            if self.running:
                self.running = False
                self.redis.close()


class SICRedisHandler(logging.Handler):
    """
    Facilities to log to Redis as a file-like object, to integrate with standard python logging facilities.

    :param redis: The Redis instance to use for logging.
    :type redis: SICRedis
    :param client_id: The client id of the device that is logging
    :type client_id: str
    """
    def __init__(self, redis, client_id):
        super(SICRedisHandler, self).__init__()
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

            # Send over Redis
            self.redis.send_message(log_channel, log_message)
        except Exception:
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
        name_ip = "[{name} {ip}]".format(
            name=record.name,
            ip=utils.get_ip_adress()
        )
        name_ip_padded = name_ip.ljust(45, '-')
        prefix = "{name_ip_padded}{color}{record_level}{reset_color}: ".format(name_ip_padded=name_ip_padded, color=color, record_level=record.levelname, reset_color=self.RESET_COLOR)

        # Split message into lines and handle each line
        message_lines = record.msg.splitlines()
        if not message_lines:
            return prefix

        # Format first line with full prefix
        formatted_lines = ["{prefix}{message_lines}".format(prefix=prefix, message_lines=message_lines[0])]

        # For subsequent lines, indent to align with first line's content
        if len(message_lines) > 1:
            indent = ' ' * len(prefix)
            formatted_lines.extend("{indent}{line}".format(indent=indent, line=line.strip()) for line in message_lines[1:])

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


def get_sic_logger(name="", client_id="", redis=None, log_level=DEBUG):
    """
    Set up logging to the log output channel to be able to report messages to users.

    :param name: A readable and identifiable name to indicate to the user where the log originated
    :type name: str
    :param client_id: The client id of the device that is logging
    :type client_id: str
    :param redis: The SICRedis object
    :type redis: SICRedis
    :param log_level: The logger.LOGLEVEL verbosity level
    :type log_level: int
    :return: The logger.
    :rtype: logging.Logger
    """
    # logging initialisation
    logger = logging.Logger(name)
    logger.setLevel(log_level)
    log_format = SICLogFormatter()

    if redis:
        # if redis is provided, use our custom handler
        handler_redis = SICRedisHandler(redis, client_id)
        handler_redis.setFormatter(log_format)
        logger.addHandler(handler_redis)
    else:
        # if there is no redis instance, this is a local device
        # make sure the SICCommonLog is subscribed to the Redis log channel
        SIC_COMMON_LOG.subscribe_to_redis_log(client_id)

        # For local logging, create a custom handler that uses SICCommonLog's file
        class SICFileHandler(logging.Handler):
            def emit(self, record):
                SIC_COMMON_LOG._write_to_logfile(self.format(record))

        # log to the terminal
        handler_terminal = logging.StreamHandler()
        handler_terminal.setFormatter(log_format)
        logger.addHandler(handler_terminal)

        # write to the logfile
        handler_file = SICFileHandler()
        handler_file.setFormatter(log_format)
        logger.addHandler(handler_file)

    return logger

# pseudo singleton object. Does nothing when this file is executed during the import, but can subscribe to the log
# channel for the user with subscribe_to_redis_log once
SIC_COMMON_LOG = SICCommonLog()