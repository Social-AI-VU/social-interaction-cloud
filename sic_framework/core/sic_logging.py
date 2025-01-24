from __future__ import print_function

import io
import logging
import threading

from . import utils
from .message_python2 import SICMessage
from .sic_redis import SICRedis


def get_log_channel():
    """
    Get the global log channel. All components on any device should log to this channel.
    """
    # TODO: add IP so each device gets its own separate log channel
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
    """An exception indicating the error happend on a remote device"""


class SICLogSubscriber(object):
    """
    A class to subscribe to a redis log channel, ensuring thread-safety with a mutex.
    """
    def __init__(self):
        self.redis = None
        self.running = False
        self.lock = threading.Lock()

    def subscribe_to_log_channel_once(self):
        """
        Subscribe to the log channel and display any messages on the terminal to propagate any log messages in the
        framework to the user. This function may be called multiple times but will only subscribe once.
        :return:
        """
        with self.lock:  # Ensure thread-safe access
            if not self.running:
                self.running = True
                self.redis = SICRedis(parent_name="SICLogSubscriber")
                self.redis.register_message_handler(
                    get_log_channel(), self._handle_log_message
                )

    def _handle_log_message(self, message):
        """
        Handle a message sent on a debug stream. Currently it's just printed to the terminal.
        :param message: SICLogMessage
        """
        print(message.msg, end="")

        if "ERROR" in message.msg.split(":")[1]:
            raise SICRemoteError("Error occurred, see remote stacktrace above.")

    def stop(self):
        with self.lock:  # Ensure thread-safe access
            if self.running:
                self.running = False
                self.redis.close()



class SICLogStream(io.TextIOBase):
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

        name_ip = "[{name} {ip}]".format(
            name=record.name,
            ip=utils.get_ip_adress()
        )

        # Pad the name_ip portion with dashes
        name_ip_padded = name_ip.ljust(40, '-')

        # Format the message with color applied to name and ip
        log_message = "{name_ip}{color}{levelname}{reset_color}: {message}".format(
            name_ip=name_ip_padded,
            color = color,
            levelname=record.levelname,
            reset_color=self.RESET_COLOR,
            message=record.msg,
        )

        return log_message


    def formatException(self, exec_info):
        """
        Prepend every exception with a | to indicate it is not local.
        """
        text = super(SICLogFormatter, self).formatException(exec_info)
        text = "| " + text.replace("\n", "\n| ")
        text += "\n| NOTE: Exception occurred in SIC framework, not application"
        return text


    def formatException(self, exec_info):
        """
        Prepend every exption with a | to indicate it is not local.
        :param exec_info:
        :return:
        """
        text = super(SICLogFormatter, self).formatException(exec_info)
        text = "| " + text.replace("\n", "\n| ")
        text += "\n| NOTE: Exception occurred in SIC framework, not application"
        return text


def get_sic_logger(name="", redis=None, log_level=logging.DEBUG):
    """
    Set up logging to the log output channel to be able to report messages to users. Also logs to the terminal.

    :param redis: The SICRedis object
    :param name: A readable and identifiable name to indicate to the user where the log originated
    :param log_level: The logger.LOGLEVEL verbosity level
    # ? still used :param log_messages_channel: the output channel of this service, on which the log output channel is based.
    """
    # logging initialisation
    logger = logging.Logger(name)
    logger.setLevel(log_level)

    # debug stream sends messages to redis
    debug_stream = SICLogStream(redis, get_log_channel())

    log_format = SICLogFormatter()

    handler_redis = logging.StreamHandler(debug_stream)
    handler_redis.setFormatter(log_format)
    logger.addHandler(handler_redis)

    handler_terminal = logging.StreamHandler()
    handler_terminal.setFormatter(log_format)
    logger.addHandler(handler_terminal)

    return logger


# loglevel interpretation, mostly follows python's defaults

CRITICAL = 50
ERROR = 40
WARNING = 30
INFO = 20  # service dependent sparse information
DEBUG = 10  # service dependent verbose information
SIC_DEBUG_FRAMEWORK = 6  # sparse messages, e.g. when executing, etc.
SIC_DEBUG_FRAMEWORK_VERBOSE = (
    4  # detailed messages, e.g. for each input output operation
)
NOTSET = 0

# pseudo singleton object. Does nothing when this file is executed during the import, but can subscribe to the log
# channel for the user with subscribe_to_log_channel_once
SIC_LOG_SUBSCRIBER = SICLogSubscriber()

def debug_framework(self, message, *args, **kws):
    if self.isEnabledFor(SIC_DEBUG_FRAMEWORK):
        # Yes, logger takes its '*args' as 'args'.
        self._log(SIC_DEBUG_FRAMEWORK, message, args, **kws)


def debug_framework_verbose(self, message, *args, **kws):
    if self.isEnabledFor(SIC_DEBUG_FRAMEWORK_VERBOSE):
        # Yes, logger takes its '*args' as 'args'.
        self._log(SIC_DEBUG_FRAMEWORK_VERBOSE, message, args, **kws)


logging.addLevelName(SIC_DEBUG_FRAMEWORK, "SIC_DEBUG_FRAMEWORK")
logging.addLevelName(SIC_DEBUG_FRAMEWORK_VERBOSE, "SIC_DEBUG_FRAMEWORK_VERBOSE")

logging.Logger.debug_framework = debug_framework
logging.Logger.debug_framework_verbose = debug_framework_verbose
