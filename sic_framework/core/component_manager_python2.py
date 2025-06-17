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
    A request from a user for this component manager, running on a device, to start a component which
    will be providing some type of capability from this device.
    """

    def __init__(self, component_type, log_level, input_channel, client_id, conf=None):
        super(SICStartComponentRequest, self).__init__()
        self.component_type = component_type  # str
        self.log_level = log_level  # logging.LOGLEVEL
        self.input_channel = input_channel
        self.client_id = client_id
        self.conf = conf  # SICConfMessage

class SICNotStartedMessage(SICMessage):
    def __init__(self, message):
        self.message = message

class SICComponentStartedMessage(SICMessage):
    def __init__(self, output_channel, request_reply_channel):
        self.output_channel = output_channel
        self.request_reply_channel = request_reply_channel

class SICComponentManager(object):
    # The maximum error between the redis server and this device's clocks in seconds
    MAX_REDIS_SERVER_TIME_DIFFERENCE = 2

    def __init__(self, component_classes, auto_serve=True):
        """
        A component manager to start components when requested by users.
        :param component_classes: List of SICService components to be started
        """

        self.stop_event = threading.Event()
        self.ready_event = threading.Event()
        self._stopping = False  # Guard to prevent multiple stop calls

        # Redis initialization
        self.redis = SICRedis(nickname="component_manager", stop_event=self.stop_event)
        self.ip = utils.get_ip_adress()

        self.active_components = []
        self.component_classes = {
            cls.get_component_name(): cls for cls in component_classes
        }
        self.component_counter = 0

        self.logger = self.get_manager_logger()
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
        Listen for requests until this component manager is signaled to stop running.
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

    def _sync_time(self):
        """
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
        Start a component on this device as requested by a user. A thread is started to run the component, and component
        threads are restarted/reused when a user re-requests the component.
        :param request: The SICStartServiceRequest request
        """

        client_id = request.client_id if request.client_id else ""

        if is_sic_instance(request, SICPingRequest):
            # this request is sent to see if the ComponentManager has started
            return SICPongMessage()

        if is_sic_instance(request, SICStopRequest):
            self.stop_event.set()
            # return an empty stop message as a request must always be replied to
            return SICSuccessMessage()
        
        # reply to the request if the component manager can start the component
        if request.component_type in self.component_classes:
            self.logger.info(
                "Handling request to start component {}".format(
                    request.component_type
                ),
                extra={"client_id": client_id}
            )

            return self.start_component(request)
        else:
            self.logger.warning(
                "{} ignored request {}".format(
                    self.__class__.__name__, request.component_type
                ),
                extra={"client_id": client_id}
            )
            return SICIgnoreRequestMessage()

    def start_component(self, request):
        """
        Start a component on this device as requested by a user. A thread is started to run the component in.
        :param request: The SICStartServiceRequest request
        :param logger: The logger for any messages from the component manager
        :return: the SICStartedServiceInformation with the information to connect to the started component.
        """

        # extract component information from the request
        component_type = request.component_type
        component_id = component_type + ":" + self.ip
        input_channel = request.input_channel
        client_id = request.client_id
        output_channel = create_data_stream_id(component_id, input_channel)
        request_reply_channel = output_channel + ":request_reply"
        log_level = request.log_level
        conf = request.conf

        component_class = self.component_classes[component_type]  # SICComponent object

        self.logger.debug("Starting component {}".format(component_type), extra={"client_id": client_id})

        component = None

        try:
            self.logger.debug("Creating threads for {}".format(component_type), extra={"client_id": client_id})
            
            component_stop_event = threading.Event()
            component_ready_event = threading.Event()
            self.logger.debug("Creating component {}".format(component_type), extra={"client_id": client_id})
            component = component_class(
                stop_event=component_stop_event,
                ready_event=component_ready_event,
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


    def connect(self, request):
        """
        Connect a component to an input channel.
        :param request: The ConnectRequest request
        :return: The SICSuccessMessage
        """
        return SICSuccessMessage()


    def get_manager_logger(self, log_level=sic_logging.DEBUG):
        """
        Create a logger to inform the user during the setup of the component by the manager.
        :param log_level: DEBUG, INFO, WARNING, ERROR, CRITICAL
        :type log_level: string
        :return: Logger
        """
        name = "{manager}".format(manager=self.__class__.__name__)

        logger = sic_logging.get_sic_logger(name=name, redis=self.redis, log_level=log_level)
        logger.info("Manager on device {} starting".format(self.ip))

        return logger
    

    def stop(self, *args):
        print("Stopping component manager")
        # import traceback
        # print("CALL STACK:")
        # traceback.print_stack()
        print("Stop event set")
        self.logger.info("Trying to exit manager gracefully...")
        try:
            # Stop all components first
            for component in self.active_components:
                print("Stopping component {}".format(component.component_id))
                component.stop()
            
            # Wait for component threads to complete (with timeout)
            timeout = 5.0  # 5 second timeout
            start_time = time.time()
            
            # Get all component threads
            component_threads = []
            for thread in threading.enumerate():
                if thread.name in [cls.get_component_name() for cls in self.component_classes.values()]:
                    component_threads.append(thread)
            
            # Wait for component threads to finish
            for thread in component_threads:
                if thread.is_alive():
                    remaining_time = timeout - (time.time() - start_time)
                    if remaining_time > 0:
                        thread.join(timeout=remaining_time)
                    else:
                        break  # Timeout reached
            
            # Close Redis last (this will wait for Redis threads to complete)
            self.redis.close()

            # print("LEFT OVER THREADS: ", threading.enumerate())
            
            self.logger.info("Graceful exit was successful")
        except Exception as err:
            self.logger.error("Graceful exit has failed: {}".format(err))