"""
component_manager_python2.py

This module contains the SICComponentManager class, used to start, stop, and manage components.
"""

import copy
import threading
import time
from signal import SIGINT, SIGTERM, signal
from sys import exit

import sic_framework.core.sic_logging
from sic_framework.core.utils import (
    MAGIC_STARTED_COMPONENT_MANAGER_TEXT,
    is_sic_instance,
)

from . import sic_logging, utils
from .message_python2 import (
    SICIgnoreRequestMessage,
    SICMessage,
    SICRequest,
    SICStopRequest,
    SICSuccessMessage,
    SICPingRequest,
    SICPongMessage
)
from .sic_redis import SICRedis


class SICStartComponentRequest(SICRequest):
    """
    A request from a user to start a component.

    :param component_name: The name of the component to start.
    :type component_name: str
    :param log_level: The logging level to use for the component.
    :type log_level: logging.LOGLEVEL
    :param conf: The configuration the component.
    :type conf: SICConfMessage
    """

    def __init__(self, component_name, log_level, conf=None):
        super(SICStartComponentRequest, self).__init__()
        self.component_name = component_name  # str
        self.log_level = log_level  # logging.LOGLEVEL
        self.conf = conf  # SICConfMessage


class SICNotStartedMessage(SICMessage):
    """
    A message to indicate that a component failed to start.

    :param message: The message to indicate the failure.
    :type message: str
    """
    def __init__(self, message):
        self.message = message


class SICComponentManager(object):
    """
    A component manager to start, stop, and manage components.

    :param component_classes: List of Components this manager can start.
    :type component_classes: list
    :param auto_serve: Whether to automatically start serving requests.
    :type auto_serve: bool
    """

    # The maximum error between the redis server and this device's clocks in seconds
    MAX_REDIS_SERVER_TIME_DIFFERENCE = 2

    # Number of seconds we wait at most for a component to start
    COMPONENT_START_TIMEOUT = 10

    def __init__(self, component_classes, auto_serve=True):
        # Redis initialization
        self.redis = SICRedis()
        self.ip = utils.get_ip_adress()

        self.active_components = []
        self.component_classes = {
            cls.get_component_name(): cls for cls in component_classes
        }
        self.component_counter = 0

        self.stop_event = threading.Event()
        self.ready_event = threading.Event()

        self.logger = self.get_manager_logger()
        self.redis.parent_logger = self.logger

        # The _handle_request function is calls execute directly, as we must reply when execution done to allow the user
        # to wait for this. New messages will be buffered by redis. The component manager listens to
        self.redis.register_request_handler(self.ip, self._handle_request)

        # TODO FIXME
        # self._sync_time()

        self.logger.info(
            MAGIC_STARTED_COMPONENT_MANAGER_TEXT
            + ' on ip "{}" with components:'.format(self.ip)
        )
        for c in self.component_classes.values():
            self.logger.info(" - {}".format(c.get_component_name()))

        self.ready_event.set()
        if auto_serve:
            self.serve()

    def serve(self):
        """
        Listen for requests to start/stop components until signaled to stop running.
        """
        # wait for the signal to stop, loop is necessary for ctrl-c to work on python2
        try:
            while True:
                self.stop_event.wait(timeout=0.1)
                if self.stop_event.is_set():
                    break
        except KeyboardInterrupt:
            pass

        self.stop()
        self.logger.info("Stopped component manager.")

    def get_manager_logger(self, log_level=sic_logging.DEBUG):
        """
        Create a logger with the name of the component manager.

        :param log_level: The logging level to use for the component manager.
        :type log_level: logging.LOGLEVEL
        :return: The logger for the component manager.
        :rtype: logging.Logger
        """
        name = "{manager}".format(manager=self.__class__.__name__)

        logger = sic_logging.get_sic_logger(name=name, redis=self.redis, log_level=log_level)
        logger.info("Manager on device {} starting".format(self.ip))

        return logger

    def start_component(self, request):
        """
        Start a component on this host as requested by a user.

        :param request: The request to start the component.
        :type request: SICStartComponentRequest
        :return: The reply to the request.
        :rtype: SICMessage
        """

        component_class = self.component_classes[request.component_name]  # SICComponent

        component = None
        try:
            stop_event = threading.Event()
            ready_event = threading.Event()
            component = component_class(
                stop_event=stop_event,
                ready_event=ready_event,
                log_level=request.log_level,
                conf=request.conf,
            )
            self.active_components.append(component)

            # TODO daemon=False could be set to true, but then the component cannot clean up properly
            # but also not available in python2
            thread = threading.Thread(target=component._start)
            thread.name = component_class.get_component_name()
            thread.start()

            # wait till the component is ready to receive input
            component._ready_event.wait(component.COMPONENT_STARTUP_TIMEOUT)

            if component._ready_event.is_set() is False:
                self.logger.error(
                    "Component {} refused to start within {} seconds!".format(
                        component.get_component_name(),
                        component.COMPONENT_STARTUP_TIMEOUT,
                    )
                )
                # Todo do something!

            # inform the user their component has started
            reply = SICSuccessMessage()

            return reply

        except Exception as e:
            self.logger.exception(
                e
            )  # maybe not needed if already sending back a not started message
            if component is not None:
                component.stop()
            return SICNotStartedMessage(e)

    def stop(self, *args):
        """
        Stop the component manager.

        Closes the redis connection and stops all active components.

        :param args: Additional arguments to pass to the stop method.
        :type args: tuple
        """
        self.stop_event.set()
        self.logger.info("Trying to exit manager gracefully...")
        try:
            self.redis.close()
            for component in self.active_components:
                component.stop()
                # component._stop_event.set()
            self.logger.info("Graceful exit was successful")
        except Exception as err:
            self.logger.error("Graceful exit has failed: {}".format(err))


    def _sync_time(self):
        """
        Sync the time of components with the time of the redis server.

        WORK IN PROGRESS: Does not work!
        clock on devices is often not correct, so we need to correct for this
        """
        # Check if the time of this device is off, because that would interfere with sensor fusion across devices
        time_diff_seconds = abs(time.time() - float("{}.{}".format(*self.redis.time())))
        if time_diff_seconds > 0.1:
            self.logger.warning(
                "Warning: device time difference to redis server is {} seconds".format(
                    time_diff_seconds
                )
            )
            self.logger.info(
                "This is allowed (max: {}), but might cause data to fused incorrectly in components.".format(
                    self.MAX_REDIS_SERVER_TIME_DIFFERENCE
                )
            )
        if time_diff_seconds > self.MAX_REDIS_SERVER_TIME_DIFFERENCE:
            raise ValueError(
                "The time on this device differs by {} seconds from the redis server (max: {}s)".format(
                    time_diff_seconds, self.MAX_REDIS_SERVER_TIME_DIFFERENCE
                )
            )

    def _handle_request(self, request):
        """
        Handle user requests such as starting/stopping components and pinging the component manager.

        :param request: The request to handle.
        :type request: SICRequest
        :return: The reply to the request.
        :rtype: SICMessage
        """

        if is_sic_instance(request, SICPingRequest):
            # this request is sent to see if the ComponentManager has started
            return SICPongMessage()

        if is_sic_instance(request, SICStopRequest):
            self.stop_event.set()
            # return an empty stop message as a request must always be replied to
            return SICSuccessMessage()
        
        # reply to the request if the component manager can start the component
        if request.component_name in self.component_classes:
            self.logger.info(
                "{} handling request to start component {}".format(
                    self.__class__.__name__, request.component_name
                )
            )

            return self.start_component(request)
        else:
            self.logger.warning(
                "{} ignored request {}".format(
                    self.__class__.__name__, request.component_name
                )
            )
            return SICIgnoreRequestMessage()