import threading
import time
from abc import ABCMeta, abstractmethod

import six

import sic_framework.core.sic_logging
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


class ConnectRequest(SICControlRequest):
    def __init__(self, input_channel, output_channel, conf=None):
        """
        A request for the component to start listening to the channel of another component (input channel).
        And to send message corresponding to that channel on the specified output channel.
        Config is optional and can be used to pass any client-specific information (such as models, session keys, etc.)

        :param input_channel: the channel of the component that serves as input to this component.
        :param output_channel: the name of the output channel of this component specific to the input channel.
        :param conf: a SICConfMessage with the parameters as fields
        """
        super(ConnectRequest, self).__init__()
        self.input_channel = input_channel  # str
        self.output_channel = output_channel  # str
        self.conf = conf  # SICConfMessage

class SICComponent:
    """
    Abstract class for services that provides functions for the Social Interaction Cloud.
    """

    __metaclass__ = ABCMeta

    # This parameter controls how long a SICConnector should wait when requesting the service
    # For example, when the robot has to stand up or model parameters need to load to GPU this might be set higher
    COMPONENT_STARTUP_TIMEOUT = 30

    def __init__(
        self, 
        ready_event=None, 
        stop_event=None, 
        log_level=sic_logging.DEBUG, 
        conf=None, 
        input_channel=None, 
        output_channel=None, 
        req_reply_channel=None,
        client_id=""
    ):
        self.log_level = log_level
        self.client_id = client_id

        # Redis and logger initialization
        try:
            self._redis = SICRedis(parent_name=self.get_component_name())
            self.logger = self._get_logger()
            self._redis.parent_logger = self.logger
            self.logger.debug("Initialized Redis and logger")
        except Exception as e:
            raise e

        self._ip = utils.get_ip_adress()
        self.component_id = self.get_component_name() + ":" + self._ip

        # the events to control this service running in the thread created by the factory
        self._ready_event = ready_event if ready_event else threading.Event()
        self._stop_event = stop_event if stop_event else threading.Event()

        # Components constrained to one input, request_reply, output channel
        self.input_channel = input_channel
        self.output_channel = output_channel
        self.request_reply_channel = req_reply_channel

        self.params = None

        self.set_config(conf)

    def _get_logger(self):
        """
        Create a logger for the component to use to send messages to the user during its lifetime.
        :param log_level: The logging verbosity level, such as DEBUG, INFO, etc.
        :return: Logger
        """
        # create logger for the component
        name = self.get_component_name()
        return sic_logging.get_sic_logger(name=name, client_id=self.client_id, redis=self._redis, log_level=self.log_level)

    def _start(self):
        """
        Wrapper for actual user implemented start to enable logging to the user.
        """
        try:
            self.start()
        except Exception as e:
            self.logger.exception(e)
            raise e

    def start(self):
        """
        Start the service. Should be called by overriding functions to communicate the service
        has started successfully.
        """
        self.logger.debug("Registering request handler")

        # register a request handler to handle requests
        self._redis.register_request_handler(
            self.request_reply_channel, self._handle_request
        )

        self.logger.debug("Request handler registered")

        self.logger.debug("Registering message handler for input channel {}".format(self.input_channel))

        # Create a closure that captures the output_channel
        def message_handler(message):
            return self.on_message(message=message)
        
        self._redis.register_message_handler(
            self.input_channel, message_handler
        )
        
        self.logger.debug("Message handler registered")

        # communicate the service is set up and listening to its inputs
        self._ready_event.set()


    def _handle_request(self, request):
        """
        An handler for control requests such as ConnectRequest. Normal Requests are passed to the on_request handler.
        Also logs the error to the remote log stream in case an exeption occured in the user-defined handler.
        :param request:
        :return:
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

    @classmethod
    def get_component_name(cls):
        """
        The display name of this component.
        """
        return cls.__name__
    
    def set_config(self, new=None):
        # Service parameter configuration
        if new:
            conf = new
        else:
            conf = self.get_conf()

        self._parse_conf(conf)

    def on_request(self, request, client_info=dict()):
        """
        Define the handler for requests. Must return a SICMessage as a reply to the request.
        :param request: The request for this component.
        :return: The reply
        :rtype: SICMessage
        """
        raise NotImplementedError("You need to define a request handler.")

    def on_message(self, client_info=dict(), message=""):
        """
        Define the handler for input messages.
        :param message: The request for this component.
        :return: The reply
        :rtype: SICMessage
        """
        raise NotImplementedError("You need to define a message handler.")

    def output_message(self, message):
        """
        Send a message on the output channel of this component.
        :param message:
        """
        message._previous_component_name = self.get_component_name()
        self._redis.send_message(self.output_channel, message)

    @staticmethod
    @abstractmethod
    def get_inputs():
        """
        Define the inputs the service needs as a list
        :return: list of SIC messages
        :rtype: List[Type[SICMessage]]
        """
        raise NotImplementedError("You need to define service input.")

    @staticmethod
    @abstractmethod
    def get_output():
        """
        Define the output of the service
        :return: SIC message
        :rtype: Type[SICMessage]
        """
        raise NotImplementedError("You need to define service output.")

    @staticmethod
    def get_conf():
        """
        Define a possible configuration using SICConfMessage
        :return: a SICConfMessage or None
        :rtype: SICConfMessage
        """
        return SICConfMessage()

    def _parse_conf(self, conf):
        """
        Helper function to parse configuration messages (SICConfMessage)
        :param conf: a SICConfMessage with the parameters as fields
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
        # TODO this needs to be synchronized with all devices, because if a nao is off by a second or two
        # its data will align wrong with other sources
        return time.time()

    def stop(self, *args):
        self.logger.debug(
            "Trying to exit {} gracefully...".format(self.get_component_name())
        )
        try:
            self._redis.close()
            self._stop_event.set()
            self.logger.debug("Graceful exit was successful")
        except Exception as err:
            self.logger.error("Graceful exit has failed: {}".format(err.message))
