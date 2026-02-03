"""
service_python2.py

This module contains the SICService class, which is the base class for all services in the Social Interaction Cloud.
"""

import collections
import logging
import threading
from abc import ABCMeta
from threading import Event

from sic_framework.core.component_python2 import SICComponent
from sic_framework.core.utils import is_sic_instance

from . import sic_logging
from .message_python2 import SICConfMessage, SICMessage
from sic_framework.core.exceptions import AlignmentError


class MessageQueue(collections.deque):
    """
    A bounded message buffer that logs warnings when messages are dropped.

    Messages are dropped when the buffer reaches MAX_MESSAGE_BUFFER_SIZE.
    Warnings are logged at exponentially increasing intervals to avoid log spam.
    """

    # Log warnings at these drop counts (exponential backoff)
    DROP_WARNING_THRESHOLDS = {5, 10, 50, 100, 200, 1000, 5000, 10000}

    def __init__(self, logger, maxlen):
        self.logger = logger
        self.dropped_messages_counter = 0
        super(MessageQueue, self).__init__(maxlen=maxlen)

    def appendleft(self, message):
        if self._is_full():
            self._handle_dropped_message(message)
        return super(MessageQueue, self).appendleft(message)

    def _is_full(self):
        return len(self) == self.maxlen

    def _handle_dropped_message(self, message):
        self.dropped_messages_counter += 1
        if self.dropped_messages_counter in self.DROP_WARNING_THRESHOLDS:
            self.logger.warning(
                "Dropped {} messages of type {}".format(
                    self.dropped_messages_counter, message.get_message_name()
                )
            )


class SICMessageDictionary:
    """
    A container for messages, indexable by message type and optionally by source component.

    Used to pass synchronized input messages to the execute() method.
    """

    def __init__(self):
        self._messages = collections.defaultdict(list)

    def add(self, message):
        """
        Add a message to the dictionary, indexed by its type.

        :param message: The message to add.
        :type message: SICMessage
        """
        self._messages[message.get_message_name()].append(message)

    def get(self, message_type, source_component=None):
        """
        Retrieve a message by type, optionally filtering by source component.

        :param message_type: The type of message to get.
        :type message_type: Type[SICMessage]
        :param source_component: Optional component to filter by.
        :return: The matching message.
        :raises IndexError: If no matching message is found.
        """
        messages = self._messages[message_type.get_message_name()]

        if not messages:
            raise AssertionError(
                "Attempting to get message from empty buffer (framework issue)"
            )

        if source_component is None:
            # No filter, return the first (should be only one)
            return messages[0]

        # Filter by source component
        source_name = self._get_component_name(source_component)
        for message in messages:
            if message._previous_component_name == source_name:
                return message

        raise IndexError(
            "Input of type {} with source: {} not found.".format(
                message_type, source_component
            )
        )

    @staticmethod
    def _get_component_name(component):
        """Extract component name from either SICComponent or SICConnector."""
        try:
            return component.get_component_name()
        except AttributeError:
            # Object is SICConnector, not SICComponent
            return component.component_class.get_component_name()


class SICService(SICComponent):
    """
    Base class for services that process and transform data.

    Services can have multiple input types. When multiple inputs are defined,
    this class automatically synchronizes incoming messages by timestamp,
    ensuring that execute() receives temporally aligned data.

    Configuration:
        MAX_MESSAGE_BUFFER_SIZE: Maximum messages to buffer per input type.
        MAX_TIMESTAMP_DIFF_SECONDS: Maximum time difference for alignment.
    """

    MAX_MESSAGE_BUFFER_SIZE = 10
    MAX_TIMESTAMP_DIFF_SECONDS = 0.5
    LISTEN_POLL_INTERVAL_SECONDS = 0.1

    def __init__(self, *args, **kwargs):
        super(SICService, self).__init__(*args, **kwargs)
        self._new_data_event = Event()
        self._input_buffers = {}
        self._listen_thread = None

    def start(self):
        """
        Start the Service.
        
        This initiates the background listener thread that handles message alignment
        and calls execute(). Because it runs in a background thread, this method
        is non-blocking, allowing subclasses to run their own loops in start() if needed.
        """
        super(SICService, self).start()
        
        self._listen_thread = threading.Thread(target=self._listen)
        self._listen_thread.daemon = True
        self._listen_thread.start()

    def execute(self, inputs):
        """
        Process synchronized input messages and optionally produce output.

        Override this method to implement your service logic.

        :param inputs: Container with time-aligned input messages.
        :type inputs: SICMessageDictionary
        :return: Output message to publish, or None.
        :rtype: SICMessage | None
        """
        pass

    # -------------------------------------------------------------------------
    # Message Handling
    # -------------------------------------------------------------------------

    def on_message(self, message):
        """
        Receive an input message and buffer it for processing.

        :param message: The incoming message.
        :type message: SICMessage
        """
        buffer_key = self._get_buffer_key(message)
        self._get_or_create_buffer(buffer_key).appendleft(message)
        self._new_data_event.set()

    def _get_buffer_key(self, message):
        """Create a unique key for buffering based on message type and source."""
        return (message.get_message_name(), message._previous_component_name)

    def _get_or_create_buffer(self, buffer_key):
        """Get existing buffer or create a new one."""
        if buffer_key not in self._input_buffers:
            self._input_buffers[buffer_key] = MessageQueue(
                self.logger, maxlen=self.MAX_MESSAGE_BUFFER_SIZE
            )
        return self._input_buffers[buffer_key]

    # -------------------------------------------------------------------------
    # Message Synchronization
    # -------------------------------------------------------------------------

    def _pop_aligned_messages(self):
        """
        Extract time-aligned messages from all input buffers.

        Finds the most recent timestamp for which all inputs have data,
        then collects one message from each buffer within the time threshold.

        :return: Tuple of (message dictionary, reference timestamp).
        :raises AlignmentError: If messages cannot be aligned.
        """
        self._log_buffer_state()
        self._validate_buffers_ready()

        reference_timestamp = self._get_reference_timestamp()
        aligned_messages = self._collect_aligned_messages(reference_timestamp)
        self._consume_messages(aligned_messages)

        message_dict = self._build_message_dict(aligned_messages)
        return message_dict, reference_timestamp

    def _log_buffer_state(self):
        """Log current buffer sizes for debugging."""
        # Only log if the logger is enabled for DEBUG
        if not self.logger.isEnabledFor(logging.DEBUG):
            return
        buffer_sizes = [(key, len(buf)) for key, buf in self._input_buffers.items()]
        self.logger.debug("Input buffer sizes: {}".format(buffer_sizes))

    def _validate_buffers_ready(self):
        """Ensure we have one buffer per expected input type."""
        expected_count = len(self.get_inputs())
        actual_count = len(self._input_buffers)
        if actual_count != expected_count:
            raise AlignmentError(
                "Waiting for all input types: have {}, need {}".format(
                    actual_count, expected_count
                )
            )

    def _get_reference_timestamp(self):
        """
        Determine the reference timestamp for alignment.

        Uses the oldest "newest message" timestamp across all buffers.
        This is the most recent time for which we have data from all sources.

        :raises AlignmentError: If any buffer is empty.
        """
        try:
            newest_per_buffer = [
                buffer[0]._timestamp for buffer in self._input_buffers.values()
            ]
            return min(newest_per_buffer)
        except IndexError:
            raise AlignmentError("One or more input buffers are empty")

    def _collect_aligned_messages(self, reference_timestamp):
        """
        Find one message per buffer that aligns with the reference timestamp.

        :param reference_timestamp: The timestamp to align to.
        :return: List of (buffer, message) tuples.
        :raises AlignmentError: If any buffer lacks an aligned message.
        """
        aligned = []
        for buffer_key, buffer in self._input_buffers.items():
            message = self._find_aligned_message(buffer, reference_timestamp)
            if message is None:
                raise AlignmentError(
                    "No message within {}s of reference timestamp in buffer {}".format(
                        self.MAX_TIMESTAMP_DIFF_SECONDS, buffer_key
                    )
                )
            aligned.append((buffer, message))
        return aligned

    def _find_aligned_message(self, buffer, reference_timestamp):
        """
        Find the first message in buffer within the timestamp threshold.

        :param buffer: The message buffer to search.
        :param reference_timestamp: The timestamp to align to.
        :return: The aligned message, or None if not found.
        """
        for message in buffer:
            time_diff = abs(message._timestamp - reference_timestamp)
            if time_diff <= self.MAX_TIMESTAMP_DIFF_SECONDS:
                return message
        return None

    def _consume_messages(self, aligned_messages):
        """Remove consumed messages from their buffers."""
        for buffer, message in aligned_messages:
            buffer.remove(message)

    def _build_message_dict(self, aligned_messages):
        """Build the message dictionary from aligned messages."""
        message_dict = SICMessageDictionary()
        for _, message in aligned_messages:
            message_dict.add(message)
        return message_dict

    # -------------------------------------------------------------------------
    # Main Loop
    # -------------------------------------------------------------------------

    def _listen(self):
        """Main loop: wait for data, align messages, and execute."""
        while not self._signal_to_stop.is_set():
            if not self._wait_for_new_data():
                continue

            try:
                messages, timestamp = self._pop_aligned_messages()
            except AlignmentError as e:
                self.logger.debug("Alignment pending: {}".format(e))
                continue

            self._process_and_output(messages, timestamp)

        # Signal to the framework that the service's worker loop has exited.
        self._stopped.set()
        self.logger.debug("Stopped listening")

    def _wait_for_new_data(self):
        """
        Wait for new data with timeout.

        :return: True if new data is available, False if timed out.
        """
        self._new_data_event.wait(timeout=self.LISTEN_POLL_INTERVAL_SECONDS)
        if not self._new_data_event.is_set():
            return False
        self._new_data_event.clear()
        return True

    def _process_and_output(self, messages, timestamp):
        """Execute the service logic and publish any output."""
        output = self.execute(messages)

        if output:
            self.logger.debug("Outputting message: {}".format(output))
            output._timestamp = timestamp
            self.output_message(output)