"""
component_manager_python2.py

This module contains the SICComponentManager class, used to start, stop, and manage components.
"""

import copy
import threading
import time
from signal import SIGINT, SIGTERM, signal
from sys import exit
import atexit
import sys, traceback

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
    :param conf: The configuration the component.
    :type conf: SICConfMessage
    """

    def __init__(self, component_name, input_channel, client_id, conf=None):
        super(SICStartComponentRequest, self).__init__()
        self.component_name = component_name  # str
        self.input_channel = input_channel
        self.client_id = client_id
        self.conf = conf  # SICConfMessage

class SICStopComponentRequest(SICRequest):
    """
    A request from a user to stop a component.

    :param component_id: The id of the component to stop. A string of characters corresponding to the output channel of the component.
    :type component_id: str
    """

    def __init__(self, component_id):
        super(SICStopComponentRequest, self).__init__()
        self.component_id = component_id  # str

class SICNotStartedMessage(SICMessage):
    """
    A message to indicate that a component failed to start.

    :param message: The message to indicate the failure.
    :type message: str
    """
    def __init__(self, message):
        self.message = message

class SICComponentStartedMessage(SICMessage):
    def __init__(self, component_channel, request_reply_channel):
        self.component_channel = component_channel
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

        self.active_components = {}
        self.component_classes = {
            cls.get_component_name(): cls for cls in component_classes
        }
        self.component_counter = 0

        self.stop_event = threading.Event()
        self.ready_event = threading.Event()

        self.name = "{}ComponentManager".format(name)
        self.logger = sic_logging.get_sic_logger(name=self.name, client_id=self.client_id, redis=self.redis, client_logger=True)
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
        if threading.current_thread() == threading.main_thread():
            self.logger.info("Registering atexit handler for component manager")
            atexit.register(self.stop)
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
        component_endpoint = component_name + ":" + self.ip
        input_channel = request.input_channel
        client_id = request.client_id
        component_channel = create_data_stream_id(component_endpoint, input_channel)
        request_reply_channel = component_channel + ":request_reply"
        conf = request.conf

        component_class = self.component_classes[component_name]  # SICComponent object

        component = None

        try:
            self.logger.debug("Creating component {}".format(component_name), extra={"client_id": client_id})
            
            stop_event = threading.Event()
            ready_event = threading.Event()
            component = component_class(
                stop_event=stop_event,
                ready_event=ready_event,
                conf=conf,
                input_channel=input_channel,
                component_channel=component_channel,
                req_reply_channel=request_reply_channel,
                client_id=client_id,
                endpoint=component_endpoint,
                ip=self.ip,
                redis=self.redis
            )
            self.logger.info("Component {} instantiated".format(component.component_endpoint), extra={"client_id": client_id})
            self.active_components[component_channel] = component
            self.logger.info("Component {} added to active components".format(component_channel), extra={"client_id": client_id})
            self.logger.critical("Active components: {}".format(self.active_components.keys()), extra={"client_id": client_id})

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

            self.logger.debug("Component {} started".format(component.component_endpoint), extra={"client_id": client_id})
            
            # register the datastreams for the component
            try:
                self.logger.debug("Setting data stream for component {}".format(component.component_endpoint), extra={"client_id": client_id})

                data_stream_info = {
                    "component_endpoint": component_endpoint,
                    "input_channel": input_channel,
                    "client_id": client_id
                }
                                
                self.redis.set_data_stream(component_channel, data_stream_info)

                self.logger.debug("Data stream set for component {}".format(component.component_endpoint), extra={"client_id": client_id})
            except Exception as e:
                self.logger.error(
                    "Error setting data stream for component {}: {}".format(component.component_endpoint, e),
                    extra={"client_id": client_id}
                )

            self.logger.debug("Component {} started successfully".format(component.component_endpoint), extra={"client_id": client_id})
            
            # inform the user their component has started
            reply = SICComponentStartedMessage(component_channel, request_reply_channel)

            return reply

        except Exception as e:
            self.logger.error(
                "Error starting component: {}".format(e),
                extra={"client_id": client_id}
            ) 
            if component is not None:
                component.stop()
            return SICNotStartedMessage(e)
    
    def stop_component(self, component_id):
        """
        Stop a component.

        :param component_id: The id of the component to stop. A string of characters corresponding to the output channel of the component.
        :type component_id: str
        """

        component = self.active_components[component_id]

        try:
            # set stop event to signal the component to stop
            component.stop()

            self.logger.debug("Unregistering component's handler threads from Redis", extra={"client_id": component.client_id})
            # unsubscribe the Component's handler threads from Redis
            self.redis.unregister_callback(component.message_handler_thread)
            self.redis.unregister_callback(component.request_handler_thread)
                
            # remove the data stream information from redis
            try:
                self.logger.debug("Removing data stream information for {}".format(component.component_endpoint), extra={"client_id": component.client_id})
                data_stream_result = self.redis.unset_data_stream(component.component_channel)

                if data_stream_result == 1:
                    self.logger.debug("Data stream information for {} removed".format(component.component_endpoint), extra={"client_id": component.client_id})
                else:
                    self.logger.debug("Data stream information for {} not found".format(component.component_endpoint), extra={"client_id": component.client_id})
            except Exception as e:
                self.logger.error("Error removing data stream information: {}".format(e), extra={"client_id": component.client_id})
                raise e
            
            del self.active_components[component_id]

            return SICSuccessMessage()
        except Exception as e:
            self.logger.error(
                "Error stopping component: {}".format(e),
                extra={"client_id": component.client_id}
            )
            return SICNotStartedMessage(e)

    def stop(self, *args):
        """
        Stop the component manager.

        Closes the redis connection and stops all active components.

        :param args: Additional arguments to pass to the stop method.
        :type args: tuple
        """
        self.logger.info("Attempting to exit manager gracefully...")
        self.stop_event.set()
        try:
            # remove the reservation for the device running this component manager
            if self.client_id != "":
                self.logger.info("Removing reservation for device {}".format(self.ip))
                self.redis.unset_reservation(self.ip)

            self.logger.info("Stopping all active components")

            for component in list(self.active_components.values()):
                component.stop()

            # self.log_live_threads(reason="before closing Redis connection")

            self.logger.info("Closing Redis connection")

            self.redis.close()
        except Exception as err:
            self.logger.error("Failed to exit manager: {}".format(err))

    def log_live_threads(self, reason=""):
        try:
            frames = sys._current_frames()
            lines = []
            lines.append("=== Live threads {} ===".format(("(" + reason + ")") if reason else ""))
            for t in threading.enumerate():
                try:
                    lines.append("Thread name='{}' ident={} daemon={} alive={}".format(t.name, t.ident, t.daemon, t.is_alive()))
                    frame = frames.get(t.ident)
                    if frame is not None:
                        stack_lines = traceback.format_stack(frame)
                        lines.extend("    " + s.rstrip() for s in stack_lines)
                except Exception as e:
                    lines.append("  <error formatting thread {}: {}>".format(t.name, e))
            message = "\n".join(lines)
            self.logger.warning(message)
        except Exception as e:
            self.logger.warning("Failed to log live threads: {}".format(e))
    

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
        
        if is_sic_instance(request, SICStartComponentRequest):
            # reply to the request if the component manager can start the component
            if request.component_name in self.component_classes:
                self.logger.info(
                    "Handling request to start component for client {}".format(
                        client_id
                    ),
                    extra={"client_id": client_id}
                )

                return self.start_component(request)
            else:
                self.logger.warning(
                    "Ignored request to start component {} as it is not in the component classes that may be started by this ComponentManager".format(
                        request.component_name
                    ),
                    extra={"client_id": client_id}
                )
                return SICIgnoreRequestMessage()
        
        if is_sic_instance(request, SICStopComponentRequest):
            # reply to the request if the component manager can stop the component
            self.logger.info(
                "Handling request to stop component for client {}".format(
                    client_id
                ),
                extra={"client_id": client_id}
            )
            if request.component_id in self.active_components:
                return self.stop_component(request.component_id)
            else:
                self.logger.critical("Active components: {}".format(self.active_components.keys()), extra={"client_id": client_id})
                self.logger.error(
                    "Ignored request to stop component with component channel {} as it is not in the active components".format(
                        request.component_id
                    ),
                    extra={"client_id": client_id}
                )
                return SICIgnoreRequestMessage()