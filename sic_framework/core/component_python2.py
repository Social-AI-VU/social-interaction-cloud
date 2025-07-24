"""
component_python2.py

This module contains the SICComponent class, which is the base class for all components in the Social Interaction Cloud.
"""

import threading
import time
from abc import ABCMeta, abstractmethod

import six

from sic_framework.core.utils import is_sic_instance
from . import sic_logging, utils
from .message_python2 import (
    SICConfMessage,
    SICControlRequest,
    SICMessage,
    SICPingRequest,
    SICPongMessage,
    SICRequest,
    SICStopRequest,
    SICSuccessMessage,
)
from .sic_redis import SICRedis

class SICComponent:
    """
    Abstract class for Components that provide essential functions for Social Interaction Cloud applications.
    
    :param ready_event: Threading event to signal when the component is ready. If None, creates a new Event.
    :type ready_event: threading.Event, optional
    :param stop_event: Threading event to signal when the component should stop. If None, creates a new Event.
    :type stop_event: threading.Event, optional
    :param log_level: The logging verbosity level (e.g., DEBUG, INFO, WARNING, ERROR).
    :type log_level: int, optional
    :param conf: Configuration parameters for the component. If None, uses default configuration.
    :type conf: dict, optional
    """

    # 1. Class constants

    # Make SICComponent an abstract class in Python 2. 
    # Ensures any subclass must implement all abstract methods denoted by @abstractmethod
    __metaclass__ = ABCMeta

    COMPONENT_STARTUP_TIMEOUT = 30
    """
    Timeout in seconds for component startup.
    
    This controls how long a SICConnector should wait when requesting a component to start.
    Increase this value for components that need more time to initialize (e.g., robots 
    that need to stand up or models that need to load to GPU).
    """

    # 2. Special methods
    def __init__(
        self, 
        ready_event=None, 
        stop_event=None, 
        log_level=sic_logging.DEBUG, 
        conf=None, 
        input_channel=None, 
        output_channel=None, 
        req_reply_channel=None,
        client_id="",
        redis=None
    ):
        self.log_level = log_level
        self.client_id = client_id

        # Redis and logger initialization
        try:
            self._redis = redis
            self.logger = sic_logging.get_sic_logger(
                name=self.get_component_name(), client_id=self.client_id, redis=self._redis
                )
            self.logger.debug("Initialized Redis and logger")
        except Exception as e:
            raise e

        self._ip = utils.get_ip_adress()
        self.component_id = self.get_component_name() + ":" + self._ip

        # _ready_event is set once the component has started, signals to the component manager that the component is ready.
        self._ready_event = ready_event if ready_event else threading.Event()
        # _stop_event is set when the component should stop
        self._stop_event = stop_event if stop_event else threading.Event()

        # Components constrained to one input, request_reply, output channel
        self.input_channel = input_channel
        self.output_channel = output_channel
        self.request_reply_channel = req_reply_channel

        self.params = None

        self.set_config(conf)
    
    # 3. Class methods
    @classmethod
    def get_component_name(cls):
        """
        Get the display name of this component.

        Returns the name of the subclass that implements this class (e.g. "DesktopCameraSensor")
        
        :return: The component's display name (typically the class name)
        :rtype: str
        """
        return cls.__name__

    # 4. Public instance methods
    def start(self):
        """
        Start the component. This method registers a request handler, signals the component is ready, 
        and logs that the component has started.

        Subclasses should call this method from their overridden start() 
        method to get the framework's default startup behavior.
        """
        self.logger.debug("Registering request handler")

        # register a request handler to handle requests
        self._redis.register_request_handler(
            self.request_reply_channel, self._handle_request
        )

        self.logger.debug("Request handler registered")

        self.logger.debug("Registering message handler for input channel {}".format(self.input_channel))

        # Create a closure for the message handler to register on the channel
        def message_handler(message):
            return self.on_message(message=message)
        
        self._redis.register_message_handler(
            self.input_channel, message_handler
        )
        
        self.logger.debug("Message handler registered")

        # communicate the service is set up and listening to its inputs
        self._ready_event.set()

        self.logger.info("Started component {}".format(self.get_component_name()))

    def stop(self, *args):
        """
        Stop the component.

        Closes the Redis connection and sets the stop event.
        
        :param args: Additional arguments (not used)
        :type args: tuple
        """
        self.logger.debug(
            "Trying to exit {} gracefully...".format(self.get_component_name())
        )
        try:
            # set stop event to signal the component to stop
            self._stop_event.set()
            
            # remove the data stream
            self.logger.debug("Removing data stream for {}".format(self.component_id))
            data_stream_result = self._redis.unset_data_stream(self.output_channel)

            if data_stream_result == 1:
                self.logger.debug("Data stream for {} removed".format(self.component_id))
            else:
                self.logger.debug("Data stream for {} not found".format(self.component_id))

            self.logger.debug("Graceful exit was successful")
        except Exception as err:
            self.logger.error("Graceful exit has failed: {}".format(err.message))

    def set_config(self, new=None):
        """
        Set the configuration for this component.

        Calls _parse_conf() to parse the configuration message.
        
        :param new: The new configuration. If None, uses the default configuration.
        :type new: SICConfMessage, optional
        """
        if new:
            conf = new
        else:
            conf = self.get_conf()

        self._parse_conf(conf)

    def on_request(self, request):
        """
        Define the handler for Component specific requests. Must return a SICMessage as a reply to the request.

        :param request: The request for this component.
        :type request: SICRequest
        :return: The reply
        :rtype: SICMessage
        """
        raise NotImplementedError("You need to define a request handler.")

    def on_message(self, message=""):
        """
        Define the handler for input messages.

        :param message: The message to handle.
        :type message: SICMessage
        :return: The reply
        :rtype: SICMessage
        """
        raise NotImplementedError("You need to define a message handler.")

    def output_message(self, message):
        """
        Send a message on the output channel of this component.

        Stores the component name in the message to allow for debugging.

        :param message: The message to send.
        :type message: SICMessage
        """
        message._previous_component_name = self.get_component_name()
        self._redis.send_message(self.output_channel, message)

    @staticmethod
    @abstractmethod
    def get_inputs():
        """
        Define the input types the component needs as a list.

        Must be implemented by the subclass.
        
        :return: list of SIC messages
        :rtype: List[Type[SICMessage]]
        """
        raise NotImplementedError("You need to define service input.")

    @staticmethod
    @abstractmethod
    def get_output():
        """
        Define the output type of the component.

        Must be implemented by the subclass.
        
        :return: SIC message
        :rtype: Type[SICMessage]
        """
        raise NotImplementedError("You need to define service output.")

    @staticmethod
    def get_conf():
        """
        Define the expected configuration of the component using SICConfMessage.
        
        :return: a SICConfMessage or None
        :rtype: SICConfMessage
        """
        return SICConfMessage()

    # 5. Protected methods
    def _start(self):
        """
        Wrapper for the user-implemented start method that provides error handling and logging.
        
        This method calls the user's start() implementation and ensures any exceptions are 
        properly logged before being re-raised to the caller.
        """
        try:
            self.start()
        except Exception as e:
            self.logger.exception(e)
            raise e

    def _handle_message(self, message):
        """
        Handle incoming messages.
        
        Calls the user-implemented on_message method to process the message.

        :param message: The message to handle.
        :type message: SICMessage
        :return: The reply to the message.
        :rtype: SICMessage
        """
        return self.on_message(message)

    def _handle_request(self, request):
        """
        Handle control requests such as SICPingRequests and SICStopRequest by calling 
        generic Component methods. Component specific requests are passed to the normal on_request handler.
        
        :param request: The request to handle.
        :type request: SICRequest
        :return: The reply to the request.
        :rtype: SICMessage
        """

        self.logger.debug(
            "Handling request {}".format(request.get_message_name())
        )

        if is_sic_instance(request, SICPingRequest):
            return SICPongMessage()

        if is_sic_instance(request, SICStopRequest):
            self.stop()
            return SICSuccessMessage()

        if not is_sic_instance(request, SICControlRequest):
            return self.on_request(request)

        raise TypeError("Unknown request type {}".format(type(request)))

    def _parse_conf(self, conf):
        """
        Parse configuration messages (SICConfMessage).
        
        This method is called by set_config() to parse the configuration message.
        
        :param conf: Configuration message to parse
        :type conf: SICConfMessage
        """
        assert is_sic_instance(conf, SICConfMessage), (
            "Configuration message should be of type SICConfMessage, "
            "is {type_conf}".format(type_conf=type(conf))
        )

        if conf == self.params:
            self.logger.info("New configuration is identical to current configuration.")
            return

        self.params = conf

    def _get_timestamp(self):
        """
        Get the current timestamp from the Redis server.
        
        :return: The current timestamp
        :rtype: float
        """
        return self._redis.time()