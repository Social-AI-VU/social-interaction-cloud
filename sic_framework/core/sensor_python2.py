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
        self.logger.debug("Setting reservation for {}".format(self.component_id))
        # set_reservation returns the number of keys set, if it is less than 1, then the reservation failed (i.e. already reserved)
        if self._redis.set_reservation(self.component_id, self.client_id) < 1:
            raise Exception("Failed to set reservation for {}, Sensor already in use".format(self.component_id))

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
        :return: A SICMessage or None if no data available
        :rtype: SICMessage or None
        """
        raise NotImplementedError("You need to define sensor execution.")

    def _produce(self):
        while not self._stop_event.is_set():
            try:    
                output = self.execute()

                # If execute returns None, it means no data is available
                if output is None and self._stop_event.is_set():
                    break
                elif output is None:
                    self.logger.warning("No data available for sensor {}".format(self.component_id))
                    continue
                    
                output._timestamp = self._get_timestamp()
                self.output_message(output)
                
            except Exception as e:
                self.logger.warning(f"Error in sensor execute: {e}")


        self.logger.debug("Stopped producing")
