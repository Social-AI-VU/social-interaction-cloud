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
    pass


class SICConnector(object):
    __metaclass__ = ABCMeta

    # define how long an "instant" reply should take at most (ping sometimes takes more than 150ms)
    _PING_TIMEOUT = 1

    def __init__(self, ip="localhost", log_level=logging.INFO, conf=None):
        """
        A proxy that enables communication with a component that has been started. We can send messages to, and receive
        from the component that is running on potentially another computer.

        :param ip: the ip adress of the device the service is running on
        :param log_level: Controls the verbosity of the connected component logging.
        :param conf: Optional SICConfMessage to set component parameters.
        """
        self._redis = SICRedis()
        assert isinstance(ip, str), "IP must be string"

        # if the component is running on the same machine
        if ip in ["localhost", "127.0.0.1"]:
            # get the ip address of the machine on the network
            ip = utils.get_ip_adress()

        self.component_name = self.component_class.get_component_name()
        self.component_ip = ip
        self.component_id = self.component_name + ":" + self.component_ip
        # client ID is the IP of whatever machine is running this connector
        self.client_id = utils.get_ip_adress()
        self._callback_threads = []
        # TODO: define client-specific request-reply channels
        self._request_reply_channel = self.component_class.get_request_reply_channel(ip)
        self._log_level = log_level
        self._conf = conf

        self.logger = self.get_connector_logger()
        self._redis.parent_logger = self.logger

        # if the component is a sensor, we need to first reserve it.
        if issubclass(self.component_class, SICSensor):
            self.logger.debug("Setting reservation for {}".format(self.component_id))
            self._redis.set_reservation(self.component_id, self.client_id)
            self.logger.debug("Defining output channel")
            self.output_channel = self.define_output_channel(self.component_id, input_stream=self.client_id)
            self.logger.debug("Output channel defined: {}".format(self.output_channel))
        else:
            # ? Keep a general output channel for non-sensors
            self.general_output_channel = self.component_class.get_general_output_channel(ip)

        # if we cannot ping the component, request it to be started from the ComponentManager
        if not self._ping():
            try:
                self._start_component()
                self.logger.debug("Component started")
                assert self._ping()
            except Exception as e:
                self.logger.error(e)
                raise RuntimeError(e)

        # if the component is not a sensor, we subscribe it to the general input channel
        # ? what are the use cases of this ?
        if not issubclass(self.component_class, SICSensor):
            self.input_channel = "{}:input:{}".format(
                self.component_class.get_component_name(), self.component_ip
            )
            self.logger.debug("Creating input channel for {}".format(self.input_channel))
            self.request(ConnectRequest(self.input_channel, self.general_output_channel), timeout=self._PING_TIMEOUT)
            self.logger.debug("Connected to {}".format(self.input_channel))
            self.output_channel = self.general_output_channel

    def _ping(self):
        try:
            self.request(SICPingRequest(), timeout=self._PING_TIMEOUT)
            self.logger.debug("RECEIVED PING RESPONSE")
            return True

        except TimeoutError:
            self.logger.error("Timeout error when trying to ping component {}".format(self.component_class.get_component_name()))
            return False

    @property
    def component_class(self):
        """
        This abstract property should be set by the subclass creating a connector for the specific component.
        e.g.
        component_class = NaoCamera
        :return: The component class this connector is for
        :rtype: type[SICComponent]
        """
        raise NotImplementedError("Abstract member component_class not set.")

    def _start_component(self):
        """
        Request the component to be started. This connector provides the input and output channels, as it determines which
        components is connected to which other components.
        log_level allows the user to control the verbosity of the connected component.

        :param component: The component we request to be started
        :param device_id: The id of the device we want to start a component on

        """
        self.logger.info(
            "Component is not already alive, requesting {} from manager {}".format(
                self.component_class.get_component_name(),
                self.component_ip,
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

        # factory returns a SICStartedComponentInformation

        try:
            component_info = self._redis.request(
                self.component_ip,
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
                        self.component_class.get_component_name(), self.component_ip
                    )
                ),
                None,
            )
        except Exception as e:
            logging.error("Unknown exception occured while trying to start {name} component: {e}".format(name=self.component_class.get_component_name(), e=e))

    def register_callback(self, output_channel, callback):
        """
        Subscribe a callback to be called when there is new data available.
        :param callback: the function to execute.
        """

        try:
            ct = self._redis.register_message_handler(output_channel, callback)
        except Exception as e:
            self.logger.error("Error registering callback: {}".format(e))
            raise e

        self._callback_threads.append(ct)

    def send_message(self, message):
        # Update the timestamp, as it should be set by the device of origin
        message._timestamp = self._get_timestamp()
        self._redis.send_message(self.input_channel, message)

    def _get_timestamp(self):
        # TODO this needs to be synchronized with all devices, because if a nao is off by a second or two
        # its data will align wrong with other sources
        # possible solution: do redis.time, and use a custom get time functions that is aware of the offset
        return time.time()

    def connect(self, input_channel=""):
        """
        Connect the output of a component to the input of this component.
        :param input_channel: The input channel to connect to
        :type input_channel: str
        :return:
        """

        input_channel_info = self._redis.get_data_stream(input_channel)
        if input_channel_info is None:
            raise ValueError("Input channel {} not found".format(input_channel))

        self.logger.debug("Defining output channel for {}".format(input_channel))
        output_channel = self.define_output_channel(self.component_id, input_channel)
        self.logger.debug("Output channel defined: {}".format(output_channel))

        request = ConnectRequest(input_channel, output_channel)
        self._redis.request(self._request_reply_channel, request)
        return output_channel

    def request(self, request, timeout=100.0, block=True):
        """
        Request data from a device. Waits until the reply is received. If the reply takes longer than
        `timeout` seconds to arrive, a TimeoutError is raised. If block is set to false, the reply is
        ignored and the function returns immediately.
        :param request: The request to the device
        :type request: SICRequest
        :param timeout: A timeout in case the action takes too long. Only works when blocking=True.
        :param block: If false, immediately returns None after sending the request.
        :return: the SICMessage reply from the device, or none if blocking=False
        :rtype: SICMessage | None
        """
        self.logger.debug("Sending request: {} over channel: {}".format(request, self._request_reply_channel))

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
        Stop the component and disconnect the callback.
        """
        self.logger.debug("Sending StopRequest to component")
        self._redis.send_message(self._request_reply_channel, SICStopRequest())
        if hasattr(self, "_redis"):
            self._redis.close()

    def get_connector_logger(self, log_level=sic_logging.DEBUG):
        """
        Create a logger to inform the user during the setup of the component by the manager.
        :param log_level: DEBUG, INFO, WARNING, ERROR, CRITICAL
        :type log_level: string
        :return: Logger
        """
        name = "{connector}Connector".format(connector=self.__class__.__name__)

        logger = sic_logging.get_sic_logger(name=name, redis=self._redis, log_level=log_level)

        return logger
    
    def define_output_channel(self, component_id, input_stream):
        """
        Define output stream for the component.
        """
        # define an output channel for this input
        data_stream_id = utils.create_data_stream_id(
            component_id=component_id,
            input_stream=input_stream
        )

        data_stream_info = {
            "component_id": component_id,
            "input_stream": input_stream
        }

        self.logger.debug("Setting data stream for {}".format(data_stream_id))
        try:
            self._redis.set_data_stream(data_stream_id, data_stream_info)
            self.logger.debug("Data stream set for {}".format(data_stream_id))
            return data_stream_id
        except Exception as e:
            self.logger.error("Error setting data stream: {}".format(e))
            raise e

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
        try:
            self.stop()
        except Exception as e:
            self.logger.error("Error in clean shutdown: {}".format(e))
