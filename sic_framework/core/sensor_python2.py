"""
sensor_python2.py

This module contains the SICSensor class, which is the base class for all sensors in the Social Interaction Cloud.
"""

from abc import abstractmethod

from sic_framework.core.component_python2 import SICComponent

from .message_python2 import SICMessage

class SICSensor(SICComponent):
    """
    Abstract class for Sensors that provide data for the Social Interaction Cloud.

    Start method calls the _produce method which calls the execute method in a loop.

    Sensors must implement the execute method individually.
    """

    def start(self):
        """
        Start the Sensor. Calls the _produce method to start producing output.
        """
        self.logger.info("Starting sensor {}".format(self.get_component_name()))

        super(SICSensor, self).start()

        self._produce()

    def on_message(self, message):
        """
        Sensors do not handle messages.
        """
        pass

    def on_request(self, request):
        """
        Sensors do not handle requests other than control requests (Start/Stop).
        """
        pass

    @abstractmethod
    def execute(self):
        """
        Main function of the sensor.

        Must be implemented by the subclass.

        :return: A SICMessage
        :rtype: SICMessage
        """
        raise NotImplementedError("You need to define sensor execution.")

    def _produce(self):
        """
        Call the execute method in a loop until the stop event is set.

        The output of the execute method is sent on the output channel.
        """
        self.logger.debug("Starting to produce")
        while not self._signal_to_stop.is_set():
            output = self.execute()

            if output is None:
                continue

            output._timestamp = self._get_timestamp()

            self.output_message(output)

        self._stopped.set()
        self.logger.debug("Stopped producing")
