"""
connector.py

This module contains the SICConnector class, the user interface to connect to components.
"""
import logging
import time
from abc import ABCMeta
import six
import sys

from sic_framework.core.sensor_python2 import SICSensor
from sic_framework.core.service_python2 import SICService
from sic_framework.core.utils import is_sic_instance, create_data_stream_id

from . import utils
from .component_manager_python2 import (
    SICNotStartedMessage, 
    SICStartComponentRequest, 
    SICStopComponentRequest,
    SICComponentStartedMessage
)
from .message_python2 import SICMessage, SICPingRequest, SICRequest, SICSuccessMessage
from . import sic_logging
from .sic_redis import SICRedisConnection
from sic_framework.core.sic_application import SICApplication


class ComponentNotStartedError(Exception):
    """
    An exception to indicate that a component failed to start.
    """
    pass


class SICConnector(object):
    """
    The user interface to connect to components wherever they are running.

    :param ip: The IP address of the component to connect to.
    :type ip: str, optional
    :param conf: The configuration for the connector.
    :type conf: SICConfMessage, optional
    """

    __metaclass__ = ABCMeta

    # define how long an "instant" reply should take at most (ping sometimes takes more than 150ms)
    _PING_TIMEOUT = 1

    def __init__(self, 
                 ip="localhost", 
                 conf=None,
                 input_source=None):

        assert isinstance(ip, str), "IP must be string"
        self.app = SICApplication()

        # connect to Redis
        self._redis = self.app.get_redis_instance()

        self.name = "{component}Connector".format(component=self.__class__.__name__)
        self.logger = sic_logging.get_sic_logger(
            name=self.name, client_id=self.app.client_ip, redis=self._redis
        )

        # if the component is running on the same machine as the Connector
        if ip in ["localhost", "127.0.0.1"]:
            # get the ip address of the current machine on the network
            ip = self.app.client_ip

        self.component_name = self.component_class.get_component_name()
        self.component_ip = ip
        self.component_endpoint = self.component_name + ":" + self.component_ip

        if input_source is None:    
            # If an input source is not provided, assume the client ID (IP address) is the input channel (i.e. Component is a Sensor/Actuator)
            # First we create a component channel with the client ID as the input source
            # Then we create an input channel with the component channel as the input source, so that the input channel is unique to the component
            self.component_channel = create_data_stream_id(self.component_endpoint, self.app.client_ip)
            self.input_channel = self.component_channel + ":input"
        else:
            # if the input channel is provided, assume the input source is a SICConnector
            if not isinstance(input_source, SICConnector):
                self.logger.error("Input source must be a SICConnector")
                self.app.shutdown()
            # If the input source is a SICConnector, we use the component channel of the input source as the input channel (already unique to the component)
            self.input_channel = input_source.get_component_channel()
            self.component_channel = create_data_stream_id(self.component_endpoint, self.input_channel)

        self.request_reply_channel = self.component_channel + ":request_reply"


        self._callback_threads = []
        self._conf = conf

        # make sure we can start the component and ping it
        try:
            self._start_component()
            self.logger.debug("Received SICComponentStartedMessage, component successfully started")
            assert self._ping(), "Component failed to ping"
        except Exception as e:
            self.logger.error(e)
            raise RuntimeError(e)

        self._callback_threads = []
        self.app.register_connector(self)
        self.logger.info("Component initialization complete")

    @property
    def component_class(self):
        """
        The component class this connector is for.

        :return: The component class this connector is for
        :rtype: type[SICComponent]
        """
        raise NotImplementedError("Abstract member component_class not set.")

    def send_message(self, message):
        """
        Send a message to the component.

        :param message: The message to send.
        :type message: SICMessage
        """
        # Update the timestamp, as it should be set by the device of origin
        message._timestamp = self._get_timestamp()
        self._redis.send_message(self.input_channel, message)

    def register_callback(self, callback):
        """
        Subscribe a callback to be called when there is new data available.

        :param callback: the function to execute.
        :type callback: function
        """

        try:
            ct = self._redis.register_message_handler(self.get_component_channel(), callback, name="{}_callback".format(self.component_endpoint))
        except Exception as e:
            self.logger.error("Error registering callback: {}".format(e))
            raise e
        
        self._callback_threads.append(ct)

    def request(self, request, timeout=100.0, block=True):
        """
        Send a request to the Component. 
        
        Waits until the reply is received. If the reply takes longer than `timeout` seconds to arrive, 
        a TimeoutError is raised. If block is set to false, the reply is ignored and the function 
        returns immediately.

        :param request: The request to send to the component.
        :type request: SICRequest
        :param timeout: A timeout in case the action takes too long.
        :type timeout: float
        :param block: If false, immediately returns None after sending the request.
        :type block: bool
        :return: the SICMessage reply from the component, or None if blocking=False
        :rtype: SICMessage | None
        """

        self.logger.debug("Sending request: {} over channel: {}".format(request, self.request_reply_channel))

        if isinstance(request, type):
            self.logger.error(
                "You probably forgot to initiate the class. For example, use NaoRestRequest() instead of NaoRestRequest."
            )

        assert utils.is_sic_instance(request, SICRequest), (
            "Cannot send requests that do not inherit from "
            "SICRequest (type: {req})".format(req=type(request))
        )

        # Update the timestamp, as it is not yet set (normally be set by the device of origin, e.g a camera)
        request._timestamp = self._get_timestamp()

        return self._redis.request(
            self.request_reply_channel, request, timeout=timeout, block=block
        )

    def stop_component(self):
        """
        Send a StopComponentRequest to the respective ComponentManager, called on exit.
        """

        self.logger.debug("Connector sending StopComponentRequest to ComponentManager")
        stop_result = self._redis.request(self.component_ip, SICStopComponentRequest(self.component_channel, self.component_name), timeout=5)
        if stop_result is None:
            self.logger.error("Stop request timed out")
            raise TimeoutError("Stop request timed out")
        if not is_sic_instance(stop_result, SICSuccessMessage):
            self.logger.error("Stop request failed")
            raise RuntimeError("Stop request failed")

        # close callback threads
        self.logger.debug("Closing callback threads")
        for ct in self._callback_threads[:]:
            self._redis.unregister_callback(ct)


    def get_input_channel(self):
        """
        Get the input channel of the component.
        """
        return self.input_channel
    
    def get_component_channel(self):
        """
        Get the output channel of the component.
        """
        return self.component_channel

    def _ping(self):
        """
        Ping the component to check if it is alive.

        :return: True if the component is alive, False otherwise.
        :rtype: bool
        """
        try:
            self.request(SICPingRequest(), timeout=self._PING_TIMEOUT)
            self.logger.debug("Received ping response")
            return True

        except TimeoutError:
            self.logger.error("Timeout error when trying to ping component {}".format(self.component_class.get_component_name()))
            return False
        
    def _start_component(self):
        """
        Request the component to be started.

        :return: The component we requested to be started
        :rtype: SICComponent
        """
        self.logger.info(
            "Component is not already alive, requesting {} from manager {}".format(
                self.component_class.get_component_name(),
                self.component_ip,
            ),
        )

        component_request = SICStartComponentRequest(
            component_name=self.component_class.get_component_name(),
            endpoint=self.component_endpoint,
            input_channel=self.input_channel,
            component_channel=self.component_channel,
            request_reply_channel=self.request_reply_channel,
            client_id=self.app.client_ip,
            conf=self._conf,
        )

        try:
            # if successful, the component manager will send a SICComponentStartedMessage,
            # which contains the ID of the output and req/reply channel
            return_message = self._redis.request(
                self.component_ip,
                component_request,
                timeout=self.component_class.COMPONENT_STARTUP_TIMEOUT,
            )
            if is_sic_instance(return_message, SICNotStartedMessage):
                raise ComponentNotStartedError(
                    "\n\nComponent did not start, error should be logged above. ({})".format(
                        return_message.message
                    )
                )
            elif is_sic_instance(return_message, SICComponentStartedMessage):
                self.logger.debug("Received SICComponentStartedMessage, component successfully started")
            else:
                self.logger.critical("Received unknown message type from component manager: {}".format(type(return_message)))
                self.app.shutdown()

        except TimeoutError as e:
            # ? Why use six.raise_from?
            six.raise_from(
                TimeoutError(
                    "Could not connect to {}. Is SIC running on the device (ip:{})?".format(
                        self.component_class.get_component_name(), self.component_ip
                    )
                ),
                None,
            )

        except Exception as e:
            logging.error("Unknown exception occured while trying to start {name} component: {e}".format(name=self.component_class.get_component_name(), e=e))

    def _get_timestamp(self):
        return self._redis.time()