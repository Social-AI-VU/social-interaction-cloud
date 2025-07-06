"""
connector.py

This module contains the SICConnector class, the user interface to connect to components.
"""


import logging
import time
from abc import ABCMeta

import six

from sic_framework.core.component_python2 import ConnectRequest
from sic_framework.core.sensor_python2 import SICSensor
from sic_framework.core.utils import is_sic_instance

from . import utils
from .component_manager_python2 import SICNotStartedMessage, SICStartComponentRequest
from .message_python2 import SICMessage, SICPingRequest, SICRequest, SICStopRequest
from . import sic_logging
from .sic_redis import SICRedis


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
    :param log_level: The logging level to use for the connector.
    :type log_level: logging.LOGLEVEL, optional
    :param conf: The configuration for the connector.
    :type conf: SICConfMessage, optional
    """
    __metaclass__ = ABCMeta

    # define how long an "instant" reply should take at most (ping sometimes takes more than 150ms)
    _PING_TIMEOUT = 1

    def __init__(self, ip="localhost", log_level=logging.INFO, conf=None):

        self._redis = SICRedis()

        assert isinstance(ip, str), "IP must be string"

        # default ip adress is local ip adress (the actual inet, not localhost or 127.0.0.1)

        if ip in ["localhost", "127.0.0.1"]:
            ip = utils.get_ip_adress()

        self._ip = ip

        self._callback_threads = []

        self._request_reply_channel = self.component_class.get_request_reply_channel(ip)
        self._log_level = log_level
        self._conf = conf

        self.logger = self.get_connector_logger()
        self._redis.parent_logger = self.logger

        self.output_channel = self.component_class.get_output_channel(self._ip)

        # if we cannot ping the component, request it to be started from the ComponentManager
        if not self._ping():
            self._start_component()

        # subscribe the component to a channel that the user is able to send a message on if needed
        self.input_channel = "{}:input:{}".format(
            self.component_class.get_component_name(), self._ip
        )
        self.request(ConnectRequest(self.input_channel), timeout=self._PING_TIMEOUT)

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

        ct = self._redis.register_message_handler(self.output_channel, callback)

        self._callback_threads.append(ct)

    def connect(self, component):
        """
        Connect the output of a component to the input of this component.

        :param component: The component connector providing the input to this component
        :type component: SICConnector
        """

        assert isinstance(
            component, SICConnector
        ), "Component connector is not a SICConnector " "(type:{})".format(
            type(component)
        )

        request = ConnectRequest(component.output_channel)
        self._redis.request(self._request_reply_channel, request)

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
            self._request_reply_channel, request, timeout=timeout, block=block
        )

    def stop(self):
        """
        Send a stop request to the component and close the redis connection.
        """

        self._redis.send_message(self._request_reply_channel, SICStopRequest())
        if hasattr(self, "_redis"):
            self._redis.close()

    def get_connector_logger(self, log_level=sic_logging.DEBUG):
        """
        Create a logger with the name of the connector.

        :param log_level: The logging level to use for the connector.
        :type log_level: logging.LOGLEVEL
        :return: The logger for the connector.
        :rtype: logging.Logger
        """
        name = "{connector}Connector".format(connector=self.__class__.__name__)

        logger = sic_logging.get_sic_logger(name=name, redis=self._redis, log_level=log_level)

        return logger

    def _ping(self):
        """
        Ping the component to check if it is alive.

        :return: True if the component is alive, False otherwise.
        :rtype: bool
        """
        try:
            self.request(SICPingRequest(), timeout=self._PING_TIMEOUT)
            return True

        except TimeoutError:
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
                self._ip,
            ),
        )

        if issubclass(self.component_class, SICSensor) and self._conf:
            self.logger.warning(
                "Setting configuration for SICSensors only works the first time connecting (sensor "
                "component instances are reused for now)"
            )

        component_request = SICStartComponentRequest(
            component_name=self.component_class.get_component_name(),
            log_level=self._log_level,
            conf=self._conf,
        )

        try:

            component_info = self._redis.request(
                self._ip,
                component_request,
                timeout=self.component_class.COMPONENT_STARTUP_TIMEOUT,
            )
            if is_sic_instance(component_info, SICNotStartedMessage):
                raise ComponentNotStartedError(
                    "\n\nComponent did not start, error should be logged above. ({})".format(
                        component_info.message
                    )
                )

        except TimeoutError as e:
            six.raise_from(
                TimeoutError(
                    "Could not connect to {}. Is SIC running on the device (ip:{})?".format(
                        self.component_class.get_component_name(), self._ip
                    )
                ),
                None,
            )
        except Exception as e:
            logging.error("Unknown exception occured while trying to start {name} component: {e}".format(name=self.component_class.get_component_name(), e=e))

    def _get_timestamp(self):
        # TODO this needs to be synchronized with all devices, because if a nao is off by a second or two
        # its data will align wrong with other sources
        # possible solution: do redis.time, and use a custom get time functions that is aware of the offset
        return time.time()

    # TODO: maybe put this in constructor to do a graceful exit on crash?
    # register cleanup to disconnect redis if an exception occurs anywhere during exection
    # TODO FIX cannot register multiple exepthooks
    # sys.excepthook = self.cleanup_after_except
    # #
    # def cleanup_after_except(self, *args):
    #     self.stop()
    #     # call original except hook after stopping
    #     sys.__excepthook__(*args)

    # TODO: maybe also helps for a graceful exit?
    def __del__(self):
        """
        Call stop() on the connector when it is deleted.
        """
        try:
            self.stop()
        except Exception as e:
            self.logger.error("Error in clean shutdown: {}".format(e))
