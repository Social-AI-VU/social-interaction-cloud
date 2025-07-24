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
    create_data_stream_id
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

    def __init__(self, component_name, log_level, input_channel, client_id, conf=None):
        super(SICStartComponentRequest, self).__init__()
        self.component_name = component_name  # str
        self.log_level = log_level  # logging.LOGLEVEL
        self.input_channel = input_channel
        self.client_id = client_id
        self.conf = conf  # SICConfMessage

class SICNotStartedMessage(SICMessage):
    """
    A message to indicate that a component failed to start.

    :param message: The message to indicate the failure.
    :type message: str
    """
    def __init__(self, message):
        self.message = message

class SICComponentStartedMessage(SICMessage):
    def __init__(self, output_channel, request_reply_channel):
        self.output_channel = output_channel
        self.request_reply_channel = request_reply_channel

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

    def __init__(self, component_classes, client_id="", auto_serve=True, name=""):
        # Redis initialization
        self.redis = SICRedis()
        self.ip = utils.get_ip_adress()
        self.client_id = client_id

        self.active_components = []
        self.component_classes = {
            cls.get_component_name(): cls for cls in component_classes
        }
        self.component_counter = 0

        self.stop_event = threading.Event()
        self.ready_event = threading.Event()

        self.name = "{}ComponentManager".format(name)
        self.logger = sic_logging.get_sic_logger(name=self.name, client_id=self.client_id, redis=self.redis)
        self.redis.parent_logger = self.logger

        # The _handle_request function is calls execute directly, as we must reply when execution done to allow the user
        # to wait for this. New messages will be buffered by redis. The component manager listens to
        self.redis.register_request_handler(self.ip, self._handle_request)

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
        

    def start_component(self, request):
        """
        Start a component on this host as requested by a user.

        :param request: The request to start the component.
        :type request: SICStartComponentRequest
        :return: The reply to the request.
        :rtype: SICMessage
        """

        # extract component information from the request
        component_name = request.component_name
        component_id = component_name + ":" + self.ip
        input_channel = request.input_channel
        client_id = request.client_id
        output_channel = create_data_stream_id(component_id, input_channel)
        request_reply_channel = output_channel + ":request_reply"
        log_level = request.log_level
        conf = request.conf

        component_class = self.component_classes[component_name]  # SICComponent object

        self.logger.debug("Starting component {}".format(component_name), extra={"client_id": client_id})

        component = None

        try:
            self.logger.debug("Creating threads for {}".format(component_name), extra={"client_id": client_id})
            
            stop_event = threading.Event()
            ready_event = threading.Event()
            self.logger.debug("Creating component {}".format(component_name), extra={"client_id": client_id})
            component = component_class(
                stop_event=stop_event,
                ready_event=ready_event,
                log_level=log_level,
                conf=conf,
                input_channel=input_channel,
                output_channel=output_channel,
                req_reply_channel=request_reply_channel,
                client_id=client_id,
                redis=self.redis
            )
            self.logger.debug("Component {} created".format(component.component_id), extra={"client_id": client_id})
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
                    ), 
                    extra={"client_id": client_id}
                )

            # register the datastreams for the component
            try:
                self.logger.debug("Setting data stream for component {}".format(component.component_id), extra={"client_id": client_id})

                data_stream_info = {
                    "component_id": component_id,
                    "input_channel": input_channel,
                    "client_id": client_id
                }
                                
                self.redis.set_data_stream(output_channel, data_stream_info)

                self.logger.debug("Data stream set for component {}".format(component.component_id), extra={"client_id": client_id})
            except Exception as e:
                self.logger.error(
                    "Error setting data stream for component {}: {}".format(component.component_id, e),
                    extra={"client_id": client_id}
                )

            self.logger.debug("Component {} started successfully".format(component.component_id), extra={"client_id": client_id})
            
            # inform the user their component has started
            reply = SICComponentStartedMessage(output_channel, request_reply_channel)

            return reply

        except Exception as e:
            self.logger.error(
                "Error starting component: {}".format(e),
                extra={"client_id": client_id}
            ) 
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
            # remove the reservation for the device running this component manager
            if self.client_id != "":
                self.logger.info("Removing reservation for device {}".format(self.ip))
                self.redis.unset_reservation(self.ip)
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
        client_id = getattr(request, "client_id", "")

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
                "Handling request to start component {}".format(
                    request.component_name
                ),
                extra={"client_id": client_id}
            )

            return self.start_component(request)
        else:
            self.logger.warning(
                "Ignored request {}".format(
                    request.component_name
                ),
                extra={"client_id": client_id}
            )
            return SICIgnoreRequestMessage()
