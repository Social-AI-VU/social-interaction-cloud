"""
component_python2.py

This module contains the SICComponent class, which is the base class for all components in the Social Interaction Cloud.
"""

import threading
import time
from abc import ABCMeta, abstractmethod

import six

from sic_framework.core.utils import is_sic_instance
from sic_framework.core.exceptions import ComponentRequestError
from . import sic_logging, utils
from .message_python2 import (
    SICConfMessage,
    SICControlRequest,
    SICPingRequest,
    SICPongMessage,
)

class SICComponent:
    """
    Abstract class for Components that provide essential functions for Social Interaction Cloud applications.
    
    :param ready_event: Threading event to signal when the component is ready. If None, creates a new Event.
    :type ready_event: threading.Event, optional
    :param stop_event: Threading event to signal when the component should stop. If None, creates a new Event.
    :type stop_event: threading.Event, optional
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

    COMPONENT_STOP_TIMEOUT = 2
    """
    Timeout in seconds for a component stop.
    
    This controls how long a SICConnector should wait when requesting a component to stop.
    Increase this value for components that need more time to stop.
    """

    # 2. Special methods
    def __init__(
        self, 
        ready_event=None, 
        stop_event=None, 
        conf=None, 
        input_channel=None, 
        component_channel=None, 
        req_reply_channel=None,
        client_id="",
        endpoint="",
        ip="",
        redis=None
    ):
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

        self._ip = ip
        self.component_endpoint = endpoint

        # _ready_event is set once the component has started, signals to the component manager that the component is ready.
        self._ready_event = ready_event if ready_event else threading.Event()
        # _signal_to_stop is set when the component should stop
        self._signal_to_stop = stop_event if stop_event else threading.Event()
        # _stopped is set when the component has stopped
        self._stopped = threading.Event()

        # Track in-flight message/request handlers to avoid cleaning up resources
        # while callbacks are still executing.
        self._active_calls_lock = threading.Lock()
        self._active_calls = 0
        self._no_active_calls = threading.Event()
        self._no_active_calls.set()

        # Components constrained to one input, request_reply, output channel
        self.input_channel = input_channel
        self.component_channel = component_channel
        self.request_reply_channel = req_reply_channel

        # Threads for the message and request handlers
        self.message_handler_thread = None
        self.request_handler_thread = None

        self.params = None
        self._threads = []

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
        self.request_handler_thread = self._redis.register_request_handler(
            self.request_reply_channel, self._handle_request, name="{}_request_handler".format(self.component_endpoint)
        )

        self.logger.debug("Request handler registered")

        self.logger.debug("Registering message handler for input channel {}".format(self.input_channel))

        # Create a closure for the message handler to register on the channel
        def message_handler(message):
            # Route through _handle_message to ensure type validation occurs
            return self._handle_message(message)
        
        self.message_handler_thread = self._redis.register_message_handler(
            self.input_channel, message_handler, name="{}_message_handler".format(self.component_endpoint) 
        )
        
        self.logger.debug("Message handler registered")

        # communicate the service is set up and listening to its inputs
        self._ready_event.set()

        self.logger.info("Successfully started!")


    def stop(self, *args):
        """
        Stop the component safely (template method).

        Lifecycle:
        - Signal the component thread to stop via `_signal_to_stop`
        - Wait (up to `COMPONENT_STOP_TIMEOUT`) for the worker thread to confirm it stopped via `_stopped`
        - Only if the worker thread has stopped, run `_cleanup()` to release subclass resources

        If the worker thread does not stop within the timeout, `_cleanup()` is skipped to avoid
        race conditions where resources are freed while the worker thread is still executing.
        """
        self._signal_to_stop.set()
        stopped = self._stopped.wait(timeout=self.COMPONENT_STOP_TIMEOUT)
        if stopped:
            self.logger.debug("Component's _stopped event set successfully")
            # Wait briefly for any in-flight request/message callbacks to finish
            # before cleaning up resources.
            self._no_active_calls.wait(timeout=self.COMPONENT_STOP_TIMEOUT)
            try:
                self._cleanup()
            except Exception as e:
                self.logger.error("Error during component cleanup: {}".format(e))
        else:
            self.logger.warning(
                "Component's _stopped event was not set within the specified timeout time; "
                "skipping cleanup to avoid race conditions"
            )

    def _cleanup(self):
        """
        Hook for subclasses to release resources.

        Called by `stop()` only after the component's worker thread has confirmed it stopped
        (i.e., `_stopped` is set). Subclasses should override this instead of overriding `stop()`.
        """
        return

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
        raise NotImplementedError("You need to define a message handler for component {}".format(self.component_endpoint))

    def output_message(self, message):
        """
        Send a message on the output channel of this component.

        Stores the component name in the message to allow for debugging.

        :param message: The message to send.
        :type message: SICMessage
        """
        message._previous_component_name = self.get_component_name()
        self._redis.send_message(self.component_channel, message)

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
        
        Validates the message against this Component's declared inputs (get_inputs) before
        dispatching to the user-implemented on_message method. Messages that do not match
        any declared input types are ignored.

        :param message: The message to handle.
        :type message: SICMessage
        :return: The reply to the message, if any.
        :rtype: SICMessage | None
        """
        # First check if the message is of a valid type
        try:
            expected_inputs = self.get_inputs()
        except Exception:
            expected_inputs = []

        # Normalize to list
        if not isinstance(expected_inputs, (list, tuple)):
            expected_inputs = [expected_inputs] if expected_inputs else []

        # If no expected inputs declared, forward as-is
        if expected_inputs:
            is_valid = any(is_sic_instance(message, input_cls) for input_cls in expected_inputs)
            if not is_valid:
                # Ignore unexpected message types to prevent component crashes
                self.logger.warning(
                    "Ignoring message of type {} not in expected inputs {}".format(
                        type(message).__name__, [c.__name__ for c in expected_inputs]
                    )
                )
                return None

        self._begin_active_call()
        try:
            return self.on_message(message)
        finally:
            self._end_active_call()

    def _handle_request(self, request):
        """
        Handle control requests such as SICPingRequests by calling generic Component methods.
        Component specific requests are passed to the normal on_request handler.
        
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

        if not is_sic_instance(request, SICControlRequest):
            self._begin_active_call()
            try:
                return self.on_request(request)
            finally:
                self._end_active_call()

        raise ComponentRequestError("Unknown request type {}".format(type(request)))

    def _begin_active_call(self):
        try:
            with self._active_calls_lock:
                self._active_calls += 1
                if self._active_calls == 1:
                    self._no_active_calls.clear()
        except Exception:
            pass

    def _end_active_call(self):
        try:
            with self._active_calls_lock:
                if self._active_calls > 0:
                    self._active_calls -= 1
                if self._active_calls == 0:
                    self._no_active_calls.set()
        except Exception:
            pass

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