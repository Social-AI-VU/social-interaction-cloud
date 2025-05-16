from abc import abstractmethod

from sic_framework.core.component_python2 import SICComponent

from .message_python2 import SICMessage

from sic_framework.core import utils

class SICSensor(SICComponent):
    """
    Abstract class for sensors that provides data for the Social Interaction Cloud.
    """

    def __init__(self, *args, **kwargs):
        super(SICSensor, self).__init__(*args, **kwargs)
        self.client_id = self._redis.get_reservation(self.component_id)
        self.output_channel = utils.create_data_stream_id(
            component_id=self.component_id,
            input_stream=self.client_id
        )

    def start(self):
        """
        Start the service. This method must be called by the user at the end of the constructor
        """
        self.logger.info("Starting sensor {}".format(self.get_component_name()))

        super(SICSensor, self).start()

        self._produce()

    @abstractmethod
    def execute(self):
        """
        Main function of the sensor
        :return: A SICMessage
        :rtype: SICMessage
        """
        raise NotImplementedError("You need to define sensor execution.")

    def _produce(self):
        while not self._stop_event.is_set():
            output = self.execute()

            output._timestamp = self._get_timestamp()

            self.output_message(self.output_channel, output)

            # self.logger.debug("Outputting message {}".format(output))

        self.logger.debug("Stopped producing")
