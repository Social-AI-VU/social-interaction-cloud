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


def get_log_channel():
    """
    Get the global log channel. All components on any device should log to this channel.
    """
    # TODO: add ID so each client/applications gets its own separate log channel
    return "sic:logging"


class SICLogMessage(SICMessage):
    def __init__(self, msg):
        """
        A wrapper for log messages to be sent over the SICRedis pubsub framework.
        :param msg: The log message to send to the user
        """
        self.msg = msg
        super(SICLogMessage, self).__init__()


class SICRemoteError(Exception):
    """An exception indicating the error happened on a remote device"""


class SICCommonLog(object):
    """
    A class to subscribe to the Redis log channel and write all log messages to a logfile.
    """
    def __init__(self):
        self.redis = None
        self.running = False
        
        # Create log filename with current date
        current_date = datetime.now().strftime("%Y-%m-%d")
        self.logfile = open("sic_{date}.log".format(date=current_date), "a")
        
        self.lock = threading.Lock()

    def subscribe_to_redis_log(self):
        """
        Subscribe to the Redis log channel and display any messages on the terminal. 
        This function may be called multiple times but will only subscribe once.
        :return:
        """
        with self.lock:  # Ensure thread-safe access
            if not self.running:
                self.running = True
                self.redis = SICRedis(parent_name="SICCommonLog")
                self.redis.register_message_handler(
                    get_log_channel(), self._handle_redis_log_message
                )

    def _handle_redis_log_message(self, message):
        """
        Handle a message sent on a debug stream. Currently it's just printed to the terminal.
        :param message: SICLogMessage
        """
        # outputs to terminal
        print(message.msg, end="")

        # writes to logfile
        self._write_to_logfile(message.msg)
    
    def _write_to_logfile(self, message):
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
        with self.lock:  # Ensure thread-safe access
            if self.running:
                self.running = False
                self.redis.close()


class SICRedisLogStream(io.TextIOBase):
    """
    Facilities to log to redis as a file-like object, to integrate with standard python logging facilities.
    """

    def __init__(self, redis, logging_channel):
        self.redis = redis
        self.logging_channel = logging_channel

    def readable(self):
        return False

    def writable(self):
        return True

    def write(self, msg):
        # only send logs to redis if a redis instance is associated with this logger
        if self.redis != None:
            message = SICLogMessage(msg)
            self.redis.send_message(self.logging_channel, message)

    def flush(self):
        return


class SICLogFormatter(logging.Formatter):
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
        """
        text = super(SICLogFormatter, self).formatException(exec_info)
        text = "| " + text.replace("\n", "\n| ")
        text += "\n| NOTE: Exception occurred in SIC framework, not application"
        return text


def get_sic_logger(name="", redis=None, log_level=DEBUG):
    """
    Set up logging to the log output channel to be able to report messages to users.

    :param redis: The SICRedis object
    :param name: A readable and identifiable name to indicate to the user where the log originated
    :param log_level: The logger.LOGLEVEL verbosity level
    """
    # logging initialisation
    logger = logging.Logger(name)

    logger.setLevel(log_level)

    log_format = SICLogFormatter()

    if redis:
        # if redis is provided, this is a remote device and we use the remote stream which sends log messages to Redis
        remote_stream = SICRedisLogStream(redis, get_log_channel())
        handler_redis = logging.StreamHandler(remote_stream)
        handler_redis.setFormatter(log_format)
        logger.addHandler(handler_redis)
    else:
        # if there is no redis instance, this is a local device
        # make sure the SICCommonLog is subscribed to the Redis log channel so all log messages are written to the logfile
        SIC_COMMON_LOG.subscribe_to_redis_log()

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