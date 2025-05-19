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
        self, ready_event=None, stop_event=None, log_level=sic_logging.INFO, conf=None
    ):
        # Redis and logger initialization
        try:
            self._redis = SICRedis(parent_name=self.get_component_name())
            self.logger = self._get_logger(log_level)
            self._redis.parent_logger = self.logger
            self.logger.debug("Initialized Redis and logger")
        except Exception as e:
            raise e

        self._ip = utils.get_ip_adress()
        self.component_id = self.get_component_name() + ":" + self._ip

        # the events to control this service running in the thread created by the factory
        self._ready_event = ready_event if ready_event else threading.Event()
        self._stop_event = stop_event if stop_event else threading.Event()

        self._input_channels = []
        self.channel_map = {}
        self._general_output_channel = self.get_general_output_channel(self._ip)

        self.params = None

        self.set_config(conf)

    def _get_logger(self, log_level):
        """
        Create a logger for the component to use to send messages to the user during its lifetime.
        :param log_level: The logging verbosity level, such as DEBUG, INFO, etc.
        :return: Logger
        """
        # create logger for the component
        name = self.get_component_name()
        return sic_logging.get_sic_logger(name=name, redis=self._redis, log_level=log_level)

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

        # register a request handler to handle control requests, e.g. ConnectRequest
        self._redis.register_request_handler(
            self.get_request_reply_channel(self._ip), self._handle_request
        )

        # communicate the service is set up and listening to its inputs
        self._ready_event.set()
        
    def _connect(self, connection_request):
        """
        Connect the output of a component to the input of this component, by registering the output channel
        to the on_message handler.
        :param connection_request: The component serving as an input to this component.
        :type connection_request: ConnectRequest
        :return:
        """
        self.logger.debug("Handling connection request")
        input_channel, output_channel, conf = connection_request.input_channel, connection_request.output_channel, connection_request.conf

        
        if input_channel in self.channel_map:
            self.logger.debug(
                "Channel {} is already connected to this input channel".format(input_channel)
            )
            return
        
        client_info = {
            "output_channel": output_channel,
        }

        # Check if component has setup_client method and call it if present
        # Setup client is a method that can be used to define any client-specific information (such as models, session keys, etc.)
        if hasattr(self, 'setup_client'):
            client_info = self.setup_client(input_channel, output_channel, conf)
            self.channel_map[input_channel] = client_info
        else:
            self.channel_map[input_channel] = client_info

        try:
            # Create a closure that captures the output_channel
            def message_handler(message):
                return self.on_message(client_info=client_info, message=message)
            
            self._redis.register_message_handler(input_channel, message_handler)

            # Client-specific request handler (not control requests)
            def request_handler(request):
                return self.on_request(request, client_info=client_info)

            # register request handler for the input channel
            self._redis.register_request_handler(input_channel + ":request_reply", request_handler)

            self.logger.debug("Connected to channel {}".format(input_channel))
        except Exception as e:
            self.logger.debug("Error connecting: {}".format(e))
            raise e
    
    # def _handle_message(self, output_channel, message):
    #     return self.on_message(output_channel=output_channel, message=message)

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

        if is_sic_instance(request, ConnectRequest):
            self._connect(request)
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

    @classmethod
    def get_general_output_channel(cls, ip):
        """
        Get the general output channel for this component.
        TODO what place is best to put this method
        TODO maybe explain why this is deterministic?
        :return: channel name
        :rtype: str
        """
        return "{name}:{ip}".format(name=cls.get_component_name(), ip=ip)

    @classmethod
    def get_request_reply_channel(cls, ip):
        """
        Get the channel name to communicate with request-replies with this component
        :return: channel name
        :rtype: str
        """

        name = cls.get_component_name()
        return "{name}:reqreply:{ip}".format(name=name, ip=ip)

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

    def output_message(self, output_channel, message):
        """
        Send a message on the output channel of this component.
        :param message:
        """
        message._previous_component_name = self.get_component_name()
        self._redis.send_message(output_channel, message)

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
